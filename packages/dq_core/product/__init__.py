"""Read-side data product aggregate over lineage and contracts."""

from .model import InboundDep, OutputPort, Product, load_all_manifests, load_manifest
from .walk import ProductAggregate, build_port_index, walk_all

__all__ = [
    "InboundDep",
    "OutputPort",
    "Product",
    "ProductAggregate",
    "build_port_index",
    "load_all_manifests",
    "load_manifest",
    "walk_all",
]
