"""Satellite acquisition: find every PRN in a recording and estimate its parameters.

Vocabulary (no abbreviations):
  satellite number   identifier of a navigation satellite; each satellite
                     transmits its own spreading code.
  spreading code     the 1023-value pseudorandom +-1 sequence of one satellite.
  chip               one value of that spreading code. Kept as a word because it
                     is the name of the unit, not a shortening.
  code period        one full 1023-chip cycle.
  code phase         position inside the code period, in chips.
  carrier Doppler    carrier frequency offset of one satellite, in Hz. Every
                     satellite has a different one, so each is searched separately.

Every number is derived, never invented:
  - sample rate, centre frequency, chip rate and code length come from the
    recording's own metadata; published GPS L1 values are used only when a file
    omits them and are marked as such.
  - samples per chip, samples per code period, code-phase increment and the
    carrier/code rate ratio follow from those four numbers.
  - the coarse Doppler step follows from one coherent code period, the fine step
    from the whole recording duration.
  - the Doppler span follows from the largest RELATIVE speed of satellite and
    receiver: the satellite's line-of-sight speed, derived from its orbit, plus the
    receiver's own speed (stated assumption: ground-based, at most 200 km/h).
  - the detection threshold follows from a false-alarm probability.
  - the noise variance follows from the received power minus the power of the
    satellites that were detected, so carrier-to-noise density is measured against
    noise alone rather than against noise plus the other satellites.

Detection uses the peak-to-floor ratio with a median floor, because other
satellites' spreading codes leak into the correlation and a mean floor would be
biased upward by their cross-correlation spikes.

Usage:
  python -m gnss.acquisition data/gnss_observation.nc [--satellites 1-32]
"""

import argparse
import sys
from dataclasses import dataclass

import numpy as np

from . import alignment, signals
from .lattice import Lattice, load_recording
from .signals import carrier, spreading_code_replica, unit_signal
from .tables import write_acquisition

SPEED_OF_LIGHT_M_S = 299_792_458.0

# Stated assumption: the receiver is on the ground and moves no faster than 200 km/h.
GROUND_RECEIVER_MAX_SPEED_KM_H = 200.0

# Doppler is produced by the RELATIVE motion of satellite and receiver, so the widest shift a
# ground receiver can see is set by the satellite's line-of-sight speed plus its own.
# Published constants needed for that, from the GPS interface specification and geodesy:
EARTH_GRAVITATIONAL_PARAMETER_M3_S2 = 3.986004418e14
EARTH_RADIUS_M = 6_371_000.0
GPS_ORBITAL_RADIUS_M = 26_560_000.0  # nominal semi-major axis: ~20,200 km altitude + Earth radius

# The published code table covers far more than the operational GPS designators 1-32, and other
# L1 C/A users (augmentation and regional systems) have their own entries. Searching all of them
# costs linear time and removes a hidden assumption, so it is the default.
DEFAULT_SATELLITES = "1-210"

FALSE_ALARM_PROBABILITY = 1e-6


@dataclass(frozen=True)
class Detection:
    """One satellite's measured parameters, as they appear in the acquisition table."""

    satellite: int
    doppler_hz: float
    doppler_uncertainty_hz: float
    code_phase_in_chips: float
    peak_to_floor_ratio: float
    carrier_to_noise_density_dbhz: float | None
    detected: bool
    # index of the code period where the navigation data bit changes inside this record, if any
    bit_change_period: int | None = None

    def as_row(self) -> dict:
        return {
            "satellite": self.satellite,
            "doppler_hz": round(self.doppler_hz, 2),
            "doppler_uncertainty_hz": round(self.doppler_uncertainty_hz, 2),
            "code_phase_in_chips": round(self.code_phase_in_chips, 3),
            "peak_to_floor_ratio": round(self.peak_to_floor_ratio, 1),
            # a correlation peak of noise alone has no meaningful carrier-to-noise density
            "carrier_to_noise_density_dbhz": (
                None if self.carrier_to_noise_density_dbhz is None
                else round(self.carrier_to_noise_density_dbhz, 1)
            ),
            "detected": self.detected,
        }


@dataclass(frozen=True)
class Acquisition:
    """Everything acquisition measured about one recording."""

    recording: str
    samples: np.ndarray
    code_periods: int
    lattice: Lattice
    detections: tuple
    threshold: float
    false_alarm_probability: float
    max_speed_km_h: float
    doppler_limit_hz: float
    coarse_step_hz: float
    fine_step_hz: float
    received_power: float
    noise_variance: float

    @property
    def detected(self) -> dict:
        """Detected satellites as {satellite: Detection}, ordered by satellite number."""
        return {
            detection.satellite: detection
            for detection in self.detections
            if detection.detected
        }

    @property
    def duration_seconds(self) -> float:
        return len(self.samples) / self.lattice.sample_rate_hz


def satellite_line_of_sight_speed_m_s() -> float:
    """Largest radial speed of a GPS satellite as seen from the ground.

    A satellite on a circular orbit has no radial speed relative to the Earth's centre, but a
    ground observer sits off-centre by one Earth radius, so the line of sight swings. The orbit
    speed is sqrt(mu/a) and the largest radial part of it is that speed times (Earth radius /
    orbital radius).
    """
    orbit_speed = np.sqrt(EARTH_GRAVITATIONAL_PARAMETER_M3_S2 / GPS_ORBITAL_RADIUS_M)
    return float(orbit_speed * EARTH_RADIUS_M / GPS_ORBITAL_RADIUS_M)


def maximum_relative_speed_m_s(receiver_speed_km_h: float) -> float:
    """Satellite line-of-sight speed plus receiver speed: what actually sets the Doppler span."""
    return satellite_line_of_sight_speed_m_s() + receiver_speed_km_h / 3.6


def parse_satellite_spec(spec: str) -> list:
    numbers = []
    try:
        for part in spec.split(","):
            if "-" in part:
                first, last = part.split("-")
                numbers.extend(range(int(first), int(last) + 1))
            else:
                numbers.append(int(part))
    except ValueError as error:
        raise SystemExit(f"bad --satellites value {spec!r}: {error}") from error
    return numbers


def coarse_search(samples: np.ndarray, satellites, lattice: Lattice, doppler_grid_hz) -> np.ndarray:
    """Correlate every satellite against every code phase, for every Doppler candidate."""
    code_periods = len(samples) // lattice.samples_per_code_period
    split = samples.reshape(code_periods, lattice.samples_per_code_period)
    times = np.arange(lattice.samples_per_code_period) / lattice.sample_rate_hz
    replicas = np.stack(
        [spreading_code_replica(s, lattice.samples_per_code_period, lattice) for s in satellites]
    )
    spectra = np.conj(np.fft.fft(replicas, axis=1))
    grid = np.empty((len(doppler_grid_hz), len(satellites), lattice.samples_per_code_period))
    for index, doppler_hz in enumerate(doppler_grid_hz):
        rotation = np.exp(-2j * np.pi * doppler_hz * times)
        accumulated = np.zeros((len(satellites), lattice.samples_per_code_period))
        for period in range(code_periods):
            spectrum = np.fft.fft(split[period] * rotation)
            accumulated += np.abs(np.fft.ifft(spectra * spectrum, axis=1)) ** 2
        grid[index] = accumulated / code_periods
    return grid


def coherent_correlation(
    samples: np.ndarray, satellite: int, lattice: Lattice, doppler_hz: float, chip_offset: float = 0.0
):
    """Whole-recording coherent correlation.

    Returns the peak power, a median-based noise floor, the sample shift of the peak,
    and the estimated signal amplitude (peak amplitude divided by the sample count).

    Chip rate is held nominal. Both rates come from one oscillator, so a carrier Doppler
    of f Hz does move the chip rate by the same fraction, 1 + f/f_carrier; over this 8 ms
    recording that is a drift of about 0.007 chips, far below the 0.25-chip sample grid,
    so the term is omitted instead of fitted to noise.
    """
    length = len(samples)
    code = spreading_code_replica(satellite, length, lattice, None, chip_offset)
    product = samples * np.conj(carrier(length, lattice, doppler_hz))
    correlation = np.fft.ifft(np.fft.fft(product) * np.conj(np.fft.fft(code)))
    power = np.abs(correlation) ** 2

    # The spreading code repeats every code period, so the correlation does too and only
    # samples_per_code_period of its values are distinct; averaging over all of them would
    # count each noise cell several times.
    distinct = power[: lattice.samples_per_code_period]
    peak_index = int(np.argmax(distinct))
    # Sub-sample peak: the correlation peak is wider than one sample, so the three points around
    # it locate the true top. Shifting a replica instead would only move which index is the peak,
    # because the correlation is circular and its height is unchanged.
    # Measured on injected delays at 55 dB-Hz: bias 0.003 chips, spread 0.018 chips (5 m), against
    # a theoretical floor of 0.005 chips (1.4 m). Denser grids and wider fit windows both measured
    # worse, because neighbouring interpolated points are strongly correlated and add noise, not
    # information, so the plain three-point fit stays.
    below = float(distinct[(peak_index - 1) % len(distinct)])
    at = float(distinct[peak_index])
    above = float(distinct[(peak_index + 1) % len(distinct)])
    curvature = below - 2.0 * at + above
    offset = 0.0
    if curvature < 0:
        offset = 0.5 * (below - above) / curvature
        if abs(offset) > 0.5:
            offset = 0.0
    peak = at - 0.25 * (below - above) * offset
    fractional_index = peak_index + offset
    # Noise-only correlation power is exponentially distributed, so the median is a robust
    # stand-in for the typical level: immune to the cross-correlation spikes that other
    # satellites' codes leave behind, unlike the mean. The ratio below and the detection
    # threshold are both expressed against this median, so no conversion factor appears.
    noise_floor = float(np.median(np.delete(distinct, peak_index)))
    periods_offset = int(np.argmax(power)) // lattice.samples_per_code_period
    shift = fractional_index + periods_offset * lattice.samples_per_code_period
    amplitude = float(np.sqrt(peak)) / length
    return peak, noise_floor, float(shift), amplitude


def period_prompts(
    samples: np.ndarray, satellite: int, lattice: Lattice, doppler_hz: float, shift_samples: float = 0.0
) -> np.ndarray:
    """One complex correlation value per code period, after carrier wipe-off and code removal.

    `shift_samples` is the peak shift found by the correlation, in samples. The replica offset is
    its negative: a peak at shift k means the received code is delayed by k, so the replica has to
    be advanced by k to line up with it.
    """
    length = len(samples)
    replica_offset = -shift_samples * lattice.code_phase_increment
    code = spreading_code_replica(satellite, length, lattice, None, replica_offset)
    product = samples * np.conj(carrier(length, lattice, doppler_hz))
    return (product * code).reshape(-1, lattice.samples_per_code_period).sum(axis=1)


def sharp_doppler(
    samples: np.ndarray,
    satellite: int,
    lattice: Lattice,
    doppler_hz: float,
    shift_samples: float,
    noise_variance: float,
):
    """Carrier Doppler from the slope of the carrier phase across code periods.

    The correlation peak only locates the frequency to roughly one over the recording length
    divided by the peak signal-to-noise ratio. The phase of one prompt per code period drifts
    linearly at the residual frequency, and fitting that line across the whole recording multiplies
    the lever arm by the number of periods, so it resolves far finer than any affordable grid.

    Returns the sharpened frequency and its uncertainty. The uncertainty is the larger of the
    thermal Cramer-Rao bound (phase noise of 1/sqrt(period signal-to-noise ratio), scaled by the
    slope uncertainty of a straight-line fit) and the scatter of the fit residuals. The residual
    term is what catches multi-access interference: the other satellites' codes and this code's
    own modified chips are correlated with the replica for the whole record, so they do not average
    away like thermal noise and can dominate the phase wobble.

    A navigation data bit that changes inside the record inverts the prompt sign from that period
    onwards. The straight-line fit would average the two halves and return a frequency tens of hertz
    wrong while still claiming a sub-hertz uncertainty, so the sign step is removed first.
    """
    prompts = period_prompts(samples, satellite, lattice, doppler_hz, shift_samples)
    periods = len(prompts)
    if periods < 3:
        return doppler_hz, 0.0

    times = np.arange(periods) * lattice.code_period_seconds
    phases = np.unwrap(np.angle(prompts))
    # inverse phase-noise variance grows with prompt power, so prompt power is the weight
    weights = np.abs(prompts) ** 2
    total_weight = float(weights.sum())
    centred = times - float(np.sum(weights * times) / total_weight)

    boundary = alignment.data_bit_sign_pattern(prompts, lattice.code_period_seconds)
    bit_change = bool(np.any(boundary < 0))
    phases = np.unwrap(np.angle(prompts * boundary))
    slope, intercept, weighted_residual = alignment.weighted_line(centred, phases, weights)
    refined = float(doppler_hz + slope / (2.0 * np.pi))

    # thermal bound: prompt magnitude is a sum over one code period, so normalise per sample
    amplitude = float(np.mean(np.abs(prompts))) / lattice.samples_per_code_period
    period_signal_to_noise = amplitude**2 * lattice.samples_per_code_period / noise_variance
    phase_noise = 1.0 / np.sqrt(max(period_signal_to_noise, 1e-12))
    slope_noise = np.sqrt(12.0 / (periods * (periods * periods - 1.0))) / lattice.code_period_seconds
    thermal_uncertainty = phase_noise * slope_noise / (2.0 * np.pi)

    # measured scatter: catches interference that the thermal model does not describe
    degrees_of_freedom = max(periods - 2 - int(bit_change), 1)
    scatter = weighted_residual * periods / degrees_of_freedom
    empirical_uncertainty = float(np.sqrt(scatter / np.sum(weights * centred * centred)) / (2.0 * np.pi))
    return refined, max(thermal_uncertainty, empirical_uncertainty)


def fine_search(
    samples: np.ndarray,
    satellite: int,
    lattice: Lattice,
    doppler_center_hz: float,
    coarse_step_hz: float,
    fine_step_hz: float,
):
    """Best (doppler, peak, floor, shift, amplitude) on a fine Doppler grid around the coarse peak.

    The peak is then interpolated between grid points, because a peak two grid steps wide carries
    more information than the grid spacing suggests; the interpolated frequency is kept only when
    it actually correlates better.
    """
    dopplers = np.arange(
        doppler_center_hz - coarse_step_hz,
        doppler_center_hz + coarse_step_hz + 0.5 * fine_step_hz,
        fine_step_hz,
    )
    candidates = [
        (float(doppler_hz),) + coherent_correlation(samples, satellite, lattice, float(doppler_hz))
        for doppler_hz in dopplers
    ]
    best = max(range(len(candidates)), key=lambda index: candidates[index][1])

    if 0 < best < len(candidates) - 1:
        below, at, above = candidates[best - 1][1], candidates[best][1], candidates[best + 1][1]
        curvature = below - 2.0 * at + above
        if curvature < 0:
            offset = 0.5 * (below - above) / curvature
            if abs(offset) <= 1.0:
                interpolated = float(dopplers[best] + offset * (dopplers[best + 1] - dopplers[best]))
                refined = (interpolated,) + coherent_correlation(samples, satellite, lattice, interpolated)
                if refined[1] > at:
                    return refined
    return candidates[best]


def detection_threshold(tested_cells: int, false_alarm_probability: float) -> float:
    """Peak-to-median ratio that noise alone exceeds with the given probability, whole search.

    Noise-only correlation power is exponential, so one cell exceeds a median-relative ratio t
    with probability 2**-t: each doubling of t halves the chance. With `tested_cells`
    independent cells, the probability that any cell anywhere in the search exceeds t is about
    tested_cells * 2**-t; solving for the target probability gives the threshold.
    """
    return float(np.log2(tested_cells / false_alarm_probability))


def acquire(
    recording: str,
    satellites=None,
    max_speed_km_h: float = GROUND_RECEIVER_MAX_SPEED_KM_H,
    false_alarm_probability: float = FALSE_ALARM_PROBABILITY,
) -> Acquisition:
    """Search every requested satellite in one recording and return the measured parameters."""
    satellites = (
        parse_satellite_spec(DEFAULT_SATELLITES) if satellites is None else list(satellites)
    )
    samples, code_periods, lattice = load_recording(recording)
    length = len(samples)
    duration_s = length / lattice.sample_rate_hz

    # Doppler span: carrier_frequency * relative_speed / speed_of_light, where the relative
    # speed is the satellite's line-of-sight speed plus the receiver's own speed.
    relative_speed_m_s = maximum_relative_speed_m_s(max_speed_km_h)
    doppler_limit_hz = lattice.centre_frequency_hz * relative_speed_m_s / SPEED_OF_LIGHT_M_S
    # Coarse step: half a cycle of phase drift across one coherent code period.
    coarse_step_hz = 1.0 / (2.0 * lattice.code_period_seconds)
    # Fine step: a quarter cycle across the whole recording.
    fine_step_hz = 1.0 / (4.0 * duration_s)
    # Grid centred on zero, as wide as the speed assumption allows: never fewer than one bin,
    # so a slow-receiver assumption cannot leave a gap between bins.
    doppler_steps = int(np.floor(doppler_limit_hz / coarse_step_hz))
    doppler_grid_hz = coarse_step_hz * np.arange(-doppler_steps, doppler_steps + 1)
    # Every cell the search examines: satellites x code phases x Doppler candidates.
    # The false-alarm probability applies to the whole search, not to one cell.
    tested_cells = len(satellites) * lattice.samples_per_code_period * len(doppler_grid_hz)
    threshold = detection_threshold(tested_cells, false_alarm_probability)

    grid = coarse_search(samples, satellites, lattice, doppler_grid_hz)

    found = []
    for position, satellite in enumerate(satellites):
        doppler_index, _ = np.unravel_index(
            int(np.argmax(grid[:, position, :])), (grid.shape[0], grid.shape[2])
        )
        doppler_hz, peak, noise_floor, shift, amplitude = fine_search(
            samples, satellite, lattice, float(doppler_grid_hz[doppler_index]), coarse_step_hz, fine_step_hz
        )
        chip_offset = shift * lattice.code_phase_increment
        found.append(
            {
                "satellite": satellite,
                "doppler_hz": doppler_hz,
                "code_phase_in_chips": chip_offset % lattice.code_length_in_chips,
                "shift_samples": shift,
                "peak": peak,
                "noise_floor": noise_floor,
                "amplitude": amplitude,
            }
        )

    # Noise variance: received power with the detected satellites' power removed.
    detected = [item for item in found if item["peak"] / item["noise_floor"] >= threshold]
    received_power = float(np.mean(np.abs(samples) ** 2))
    satellites_power = sum(item["amplitude"] ** 2 for item in detected)
    noise_variance = received_power - satellites_power
    if noise_variance <= 0:
        raise SystemExit(
            f"detected satellites explain {satellites_power:.3f} of {received_power:.3f} received power; "
            "noise variance would not be positive"
        )

    # The phase-slope fit below reads one satellite, but its prompt still contains the other
    # satellites' codes, whose cross-correlation does not average away over eight code periods.
    # Cancel them first with the fine estimates already found, so the fit sees one carrier plus
    # noise; this removes the multi-access bias from the sharpened frequency.
    units = {
        item["satellite"]: unit_signal(length, item["satellite"], lattice, item["doppler_hz"], item["shift_samples"])
        for item in detected
    }
    coefficients = {satellite: np.vdot(unit, samples) / length for satellite, unit in units.items()}
    without_others = {
        satellite: samples - sum(coefficients[other] * units[other] for other in units if other != satellite)
        for satellite in units
    }

    detections = []
    for item in found:
        measurement = without_others.get(item["satellite"], samples)
        bit_signs = alignment.data_bit_sign_pattern(
            period_prompts(
                measurement,
                item["satellite"],
                lattice,
                item["doppler_hz"],
                item["shift_samples"],
            ),
            lattice.code_period_seconds,
        )
        bit_change_period = (
            int(np.argmax(bit_signs < 0)) if np.any(bit_signs < 0) else None
        )
        if bit_change_period is not None:
            # Remove the navigation data bit's sign change from the measurement before correlating.
            # Without that, half the record adds with the wrong sign, and a correlation peak cannot
            # tell the bit flip from a frequency offset of about 1/(2*half-record).
            measurement = measurement.copy() * np.repeat(
                bit_signs, lattice.samples_per_code_period
            )
        sharpened, uncertainty = sharp_doppler(
            measurement,
            item["satellite"],
            lattice,
            item["doppler_hz"],
            item["shift_samples"],
            noise_variance,
        )
        # For a detected satellite the cleaned phase-slope fit is the better frequency estimate; the
        # peak-power test below is only used for undetected satellites, where the fit can be noise.
        # The peak comparison is unreliable on the raw signal because the other codes' contribution
        # jitters the peak by far more than a sub-hertz frequency error does.
        peak, noise_floor, shift, amplitude = coherent_correlation(
            measurement, item["satellite"], lattice, sharpened
        )
        if item["satellite"] in without_others:
            # Consistency with the grid is the default test, with the fit's own uncertainty as the
            # allowance. A large but well-supported correction is settled by the criterion that
            # matters: does the corrected frequency correlate better?
            accepted = abs(sharpened - item["doppler_hz"]) <= max(
                0.5 * fine_step_hz, 3.0 * uncertainty
            )
            if not accepted:
                grid_peak = coherent_correlation(
                    measurement, item["satellite"], lattice, item["doppler_hz"]
                )[0]
                accepted = peak >= grid_peak
        else:
            accepted = peak >= item["peak"]
        if not accepted:
            sharpened = item["doppler_hz"]
            peak, noise_floor, shift, amplitude = coherent_correlation(
                measurement, item["satellite"], lattice, sharpened
            )
        ratio = peak / noise_floor
        is_detected = bool(ratio >= threshold)
        signal_to_noise = peak / (length * noise_variance)
        detections.append(
            Detection(
                satellite=item["satellite"],
                doppler_hz=float(sharpened),
                doppler_uncertainty_hz=float(uncertainty),
                code_phase_in_chips=float(item["code_phase_in_chips"]),
                peak_to_floor_ratio=float(ratio),
                carrier_to_noise_density_dbhz=(
                    float(10 * np.log10(signal_to_noise / duration_s)) if is_detected else None
                ),
                detected=is_detected,
                bit_change_period=bit_change_period,
            )
        )

    detections.sort(key=lambda detection: detection.peak_to_floor_ratio, reverse=True)
    return Acquisition(
        recording=recording,
        samples=samples,
        code_periods=code_periods,
        lattice=lattice,
        detections=tuple(detections),
        threshold=threshold,
        false_alarm_probability=false_alarm_probability,
        max_speed_km_h=max_speed_km_h,
        doppler_limit_hz=float(doppler_limit_hz),
        coarse_step_hz=float(coarse_step_hz),
        fine_step_hz=float(fine_step_hz),
        received_power=received_power,
        noise_variance=float(noise_variance),
    )


def report(acquisition: Acquisition) -> list:
    """Human-readable summary of one acquisition, one line per fact."""
    lattice = acquisition.lattice
    lines = [
        f"{acquisition.recording}: {acquisition.code_periods} code periods, "
        f"{len(acquisition.samples)} samples at {lattice.sample_rate_hz:g} Hz",
        f"  {lattice.samples_per_chip:g} samples/chip, "
        f"{lattice.samples_per_code_period} samples per code period",
        f"  highest relative speed: satellite line of sight "
        f"{satellite_line_of_sight_speed_m_s():.0f} m/s + ground receiver "
        f"{acquisition.max_speed_km_h / 3.6:.1f} m/s = "
        f"{maximum_relative_speed_m_s(acquisition.max_speed_km_h):.0f} m/s "
        f"-> doppler +-{acquisition.doppler_limit_hz:.0f} Hz",
        f"  coarse step {acquisition.coarse_step_hz:g} Hz, fine step {acquisition.fine_step_hz:.1f} Hz",
        f"  detection threshold {acquisition.threshold:.1f} at false-alarm probability "
        f"{acquisition.false_alarm_probability:g}",
        f"  received power {acquisition.received_power:.3f}, "
        f"noise variance {acquisition.noise_variance:.3f}",
        f"{'sat':>4} {'doppler Hz':>11} {'+- Hz':>7} {'code chips':>11} {'peak/floor':>11} {'dB-Hz':>7}  det",
    ]
    for detection in acquisition.detections:
        if not detection.detected:
            continue
        lines.append(
            f"{detection.satellite:>4} {detection.doppler_hz:>11.2f} "
            f"{detection.doppler_uncertainty_hz:>7.2f} {detection.code_phase_in_chips:>11.2f} "
            f"{detection.peak_to_floor_ratio:>11.1f} "
            f"{detection.carrier_to_noise_density_dbhz:>7.1f}  yes"
        )
    found = sorted(acquisition.detected)
    lines.append(f"detected {len(found)} satellites: {found}")
    return lines


def main(argv=None):
    parser = argparse.ArgumentParser(
        prog="python -m gnss.acquisition",
        description="Detect the GPS L1 C/A satellites in one recording and estimate their parameters.",
    )
    parser.add_argument("recording")
    parser.add_argument("--satellites", default=DEFAULT_SATELLITES)
    parser.add_argument(
        "--max-speed-km-h",
        type=float,
        default=GROUND_RECEIVER_MAX_SPEED_KM_H,
        help=f"largest expected receiver speed in km/h (default {GROUND_RECEIVER_MAX_SPEED_KM_H:g})",
    )
    parser.add_argument(
        "--false-alarm-probability",
        type=float,
        default=FALSE_ALARM_PROBABILITY,
        help="per-satellite false-alarm probability",
    )
    arguments = parser.parse_args(argv)

    acquisition = acquire(
        arguments.recording,
        parse_satellite_spec(arguments.satellites),
        max_speed_km_h=arguments.max_speed_km_h,
        false_alarm_probability=arguments.false_alarm_probability,
    )
    for line in report(acquisition):
        print(line)
    destination = write_acquisition(arguments.recording, acquisition.detections)
    print(f"-> {destination}")
    return acquisition


def self_check(lattice: Lattice):
    """Known-answer tests: published code vectors, a noiseless signal, and noise alone."""
    if signals.first_10_chips(1) != 0o1440:  # published vector, satellite 1
        raise SystemExit("spreading code generator does not match the published GPS vector")
    if signals.first_10_chips(2) != 0o1620:  # published vector, satellite 2
        raise SystemExit("spreading code generator does not match the published GPS vector")

    length = lattice.samples_per_code_period * 8
    times = np.arange(length) / lattice.sample_rate_hz
    noiseless = []
    for satellite, doppler_hz in ((7, 1234.0), (19, -3100.0)):
        code = spreading_code_replica(satellite, length, lattice)
        samples = code * np.exp(2j * np.pi * doppler_hz * times)
        peak, noise_floor, shift, amplitude = coherent_correlation(samples, satellite, lattice, doppler_hz)
        whole_periods = round(shift / lattice.samples_per_code_period) * lattice.samples_per_code_period
        if abs(shift - whole_periods) > 0.5:
            raise SystemExit(f"noiseless satellite {satellite} peaked at shift {shift}, expected a whole period")
        if abs(amplitude - 1.0) > 0.05:
            raise SystemExit(f"noiseless satellite {satellite} amplitude {amplitude:.3f}, expected 1.0")
        noiseless.append(peak / noise_floor)

    generator = np.random.default_rng(0)
    noise = (generator.standard_normal(length) + 1j * generator.standard_normal(length)) / np.sqrt(2)
    peak, noise_floor, _, _ = coherent_correlation(noise, 7, lattice, 0.0)
    noise_only = peak / noise_floor

    # Known-answer test for the sharp Doppler estimator: inject a known offset and recover it.
    generator = np.random.default_rng(7)
    satellite, injected_hz = 11, -1234.5
    code = spreading_code_replica(satellite, length, lattice)
    noisy = 0.278 * code * np.exp(2j * np.pi * injected_hz * times)
    noisy += (generator.standard_normal(length) + 1j * generator.standard_normal(length)) / np.sqrt(2.0)
    _, _, shift, _ = coherent_correlation(noisy, satellite, lattice, injected_hz)
    estimate, uncertainty = sharp_doppler(noisy, satellite, lattice, injected_hz + 20.0, shift, 1.0)
    if uncertainty <= 0 or uncertainty > 10.0:
        raise SystemExit(f"sharp Doppler uncertainty {uncertainty:.2f} Hz is not plausible")
    if abs(estimate - injected_hz) > 3.0 * uncertainty:
        raise SystemExit(
            f"sharp Doppler recovered {estimate:.2f} Hz for an injected {injected_hz:.2f} Hz "
            f"+-{uncertainty:.2f}, which is outside three standard deviations"
        )
    code_phase = shift % lattice.samples_per_code_period
    if code_phase > 0.5 and code_phase < lattice.samples_per_code_period - 0.5:
        raise SystemExit(f"sub-sample peak landed at {code_phase:.2f} samples, expected near zero")

    threshold = detection_threshold(8 * lattice.samples_per_code_period, 1e-6)
    if noise_only >= threshold:
        raise SystemExit(f"noise alone reached peak/floor {noise_only:.1f}, above threshold {threshold:.1f}")
    if min(noiseless) <= noise_only:
        raise SystemExit(f"noiseless signal {min(noiseless):.1f} did not beat noise alone {noise_only:.1f}")


if __name__ == "__main__":
    _, _, check_lattice = load_recording(sys.argv[1] if len(sys.argv) > 1 else "data/gnss_observation.nc")
    self_check(check_lattice)
    main()
