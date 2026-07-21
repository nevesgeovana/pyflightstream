"""Managed run file layout.

Pipeline role: owns where run files live. Folder layout, staging of solver
inputs, collection of outputs, and archiving are managed by the package,
not by the user: folder identity mistakes were a recurring failure mode in
the predecessor toolchain. Run identity lives in the manifest, never in
folder names.

Implemented at milestone M2.
"""
