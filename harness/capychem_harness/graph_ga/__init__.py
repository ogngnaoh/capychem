"""Vendored Jensen GB-GA operators (RDKit + numpy, no PyTorch).

Copied verbatim from mol_opt (wenhao-gao/mol_opt, main/graph_ga/), which vendors
them from jensengroup/GB_GA. Harness-internal only — modern code reaches Graph-GA
through ``propose.py`` via subprocess, never by import.
"""
