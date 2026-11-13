# מקורות: אות GPS L1 C/A והמודם

המקורות עצמם באנגלית — אין להם תרגום. ההערות אומרות למה כל מקור טוב ומתי להשתמש בו.

## Knowledge

- [Book (open access): _A Software-Defined GPS and Galileo Receiver_ — Borre, Akos, Bertelsen, Rinder & Jensen](https://link.springer.com/book/10.1007/978-0-8176-4540-3)
  The best free, receiver-engineer-first text. Use for: signal structure (§3.1–3.3), FFT acquisition (§6), tracking loops (§7), and Matlab-style derivations that match this workspace's Python.
- [Spec: IS-GPS-200N, GPS interface specification (3.3 MB PDF)](https://www.navcen.uscg.gov/sites/default/files/pdf/gps/IS-GPS-200N.pdf)
  The authority on chip-level truth. Use for: C/A code generation (§3.3, Table 3-Ia), signal parameters (§3.2.1.1), nav-message bit layout (§20). Blocked to some scripted fetchers — open in a browser.
- [Reference: ESA Navipedia — GPS Signal Plan](https://gssc.esa.int/navipedia/index.php/GPS_Signal_Plan)
  One-page table of every GPS signal's modulation, chip rate, band. Use for: quick constant lookups and comparisons to L2/L5/L1C.
- [Reference: ESA Navipedia — GPS C1, P1 and P2 codes and receiver types](https://gssc.esa.int/navipedia/index.php/GPS_C1,_P1_and_P2_Codes_and_Receiver_Types)
  Covers C/A code properties, Gold-code family, correlation bounds. Use for: "how separable are two PRNs, really".
- [Reference: ESA Navipedia — Autocorrelation &amp; Power Spectral Density](https://gssc.esa.int/navipedia/index.php/Autocorrelation_%26_Power_Spectral_Density)
  Use for: the triangular autocorrelation shape and the sinc² spectrum, with plots.
- [Docs: GNSS-SDR acquisition blocks](https://gnss-sdr.org/docs/sp-blocks/acquisition/)
  Practical description of PCPS/FFT acquisition as implemented in a real open-source receiver. Use for: acquisition thresholds, dwell time, detection metrics.
- [Code: Peter Monta, GNSS-DSP-tools](https://github.com/pmonta/GNSS-DSP-tools)
  Small, readable Python kernels for many signals; `gnsstools/gps/ca.py` is the C/A generator, vendored (MIT, trimmed) in `vendor/` and reached through `gnss/vendor.py`. Use for: a trusted reference implementation to diff against your own code.
- [Reference: ESA Navipedia — GPS Navigation Message](https://gssc.esa.int/navipedia/index.php/GPS_Navigation_Message)
  Subframe/word structure, TLM/HOW. Use for: frame sync, 20 ms bit boundaries, ephemeris layout.

## Wisdom (Communities)

- [r/GNSS](https://reddit.com/r/GNSS)
  Small but genuinely technical; practitioners from receivers, surveying, and SDR. Use for: sanity checks on processing choices, "is this peak real" questions.
- [GNSS-SDR mailing list / GitHub issues](https://github.com/gnss-sdr/gnss-sdr/issues)
  Where receiver bugs actually get diagnosed by people who build receivers. Use for: acquisition/tracking pathology questions.
- [nav-sdr discussion group](https://groups.io/g/nav-sdr)
  Low traffic, long history; the SDR-GNSS crowd (antenna → correlator). Use for: raw-sample workflow questions.

*Community preferences: none stated yet. Confirm before proposing any local meetup or paid course.*

## Gaps

- No free source found yet that covers **multi-PRN structured chip modification / code-domain watermarking**. Likely covered only in research literature (signal authentication: TESLA-style spread-spectrum watermarking, OSNMA). Search needed before Lesson 3.
- No good free source yet on **DLL/PLL discriminator design trade-offs at low C/N0** beyond Borre's chapter 7. Consider Ward's "Performance comparisons of FLL/PLL" if a PDF surfaces.
