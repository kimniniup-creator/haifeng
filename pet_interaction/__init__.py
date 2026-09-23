"""Pet interaction policy. Importing this package never opens hardware or services."""

from .controller import PetController

__all__ = ["PetController"]
