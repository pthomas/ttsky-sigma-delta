# References

Definitive claims in this document lean on the standard literature; the
numbered markers in the text point here.

1. R. Schreier and G. C. Temes, *Understanding Delta-Sigma Data
   Converters*, IEEE Press / Wiley, 2005. The canonical text: the
   first-order signal-to-quantization-noise formula
   SQNR = 6.02·N + 1.76 − 10·log₁₀(π²/3) + 30·log₁₀(OSR) dB (whose OSR
   term is the "9 dB per doubling" statement), and the analysis of
   first-order idle tones / pattern noise that makes the linear formula
   optimistic.
2. B. E. Boser and B. A. Wooley, "The Design of Sigma-Delta Modulation
   Analog-to-Digital Converters," *IEEE Journal of Solid-State Circuits*,
   vol. 23, no. 6, 1988. Classic treatment of implementation
   non-idealities, including why feedback-pulse energy must be
   bit-history independent (inter-symbol interference).
3. J. A. Cherry and W. M. Snelgrove, "Excess Loop Delay in
   Continuous-Time Delta-Sigma Modulators," *IEEE Transactions on
   Circuits and Systems II*, vol. 46, no. 4, 1999. Why loop delay is a
   first-class design parameter in continuous-time modulators rather
   than a refinement.
4. B. Razavi, "The StrongARM Latch [A Circuit for All Seasons]," *IEEE
   Solid-State Circuits Magazine*, vol. 7, no. 2, 2015. Operation,
   offset, and design practice of the StrongARM comparator, including
   the output buffering this project re-learned the hard way.
5. M. Ortmanns and F. Gerfers, *Continuous-Time Sigma-Delta A/D
   Conversion*, Springer, 2006. Continuous-time specifics: return-to-zero
   vs non-return-to-zero feedback, jitter sensitivity trades.
