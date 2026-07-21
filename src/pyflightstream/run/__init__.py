"""Execution of FlightStream and the run manifest.

Pipeline role: runs the solver headless on generated scripts (local
executable or HPC submission) and records every datapoint in the campaign
manifest with its convergence status, versions, and input hashes. Silent
skips are structurally impossible: every failure lands in the manifest and
the campaign raises a summary error at the end.

Implemented at milestone M2.
"""
