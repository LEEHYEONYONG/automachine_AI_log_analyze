import { Bloom, EffectComposer, N8AO, ToneMapping, Vignette } from "@react-three/postprocessing";
import { ToneMappingMode } from "postprocessing";

/** Screen-space finish: soft contact shading, glow on lamps brighter than white, and a darker frame. */
export function Effects() {
  return (
    <EffectComposer multisampling={4}>
      <N8AO aoRadius={0.5} distanceFalloff={0.5} intensity={4} quality="medium" halfRes />
      <Bloom mipmapBlur luminanceThreshold={1} luminanceSmoothing={0.2} intensity={0.6} />
      {/* The composer renders to a texture, which skips the renderer's own tone mapping. */}
      <ToneMapping mode={ToneMappingMode.ACES_FILMIC} />
      <Vignette offset={0.3} darkness={0.35} />
    </EffectComposer>
  );
}
