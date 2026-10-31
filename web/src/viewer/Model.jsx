import { Clone, useGLTF } from "@react-three/drei";

// Built by web/models/machine.py. Each node is one rigid group, in that group's own coordinates.
const MODEL = "/models/machine.glb";

/** One named piece of the machine's hardware. Scene wraps the machine in Suspense while the file loads. */
export function Model({ name }) {
  const { nodes } = useGLTF(MODEL);
  return <Clone object={nodes[name]} castShadow receiveShadow />;
}

useGLTF.preload(MODEL);
