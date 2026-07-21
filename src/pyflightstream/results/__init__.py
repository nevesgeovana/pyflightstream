"""Anchor-based parsers for FlightStream output files.

Pipeline role: reads solver output text files into typed results. Values
are located by their printed labels and tables by their header rows, never
by fixed line numbers, so cosmetic layout changes between FlightStream
versions do not silently corrupt data. A missing footer means the file is
incomplete and is reported as such. The FlightStream version printed in
each output is cross-checked against the requested version.

Implemented at milestone M2.
"""
