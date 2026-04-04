"""Scene registry — cenas plugaveis para renderizacao."""

from server.renderer.scenes.base import RenderContext, SceneRenderer
from server.renderer.scenes.crypto import CryptoScene
from server.renderer.scenes.panoramic import PanoramicScene
from server.renderer.scenes.vitoria_sports import VitoriaSportsScene

SCENE_REGISTRY: dict[str, SceneRenderer] = {
    "vitoria_sports": VitoriaSportsScene(),
    "panoramic": PanoramicScene(),
    "crypto": CryptoScene(),
}

__all__: list[str] = [
    "RenderContext",
    "SceneRenderer",
    "SCENE_REGISTRY",
]
