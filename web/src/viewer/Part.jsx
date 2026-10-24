import { useFrame } from "@react-three/fiber";
import { forwardRef, useRef } from "react";

import { Housing } from "./details";
import { BEAD_LENGTHS, BEAD_SEGMENTS, BEAD_STARTS, BEAD_TOTAL, COLORS, PART } from "./layout";

const BEAD_W = 0.025;
const BEAD_H = 0.014;

/** Adhesive bead drawn up to `fraction()` of its length, updated every frame. */
function Bead({ fraction, color }) {
  const meshes = useRef([]);

  useFrame(() => {
    const done = fraction() * BEAD_TOTAL;
    BEAD_SEGMENTS.forEach((seg, i) => {
      const mesh = meshes.current[i];
      if (!mesh) return;
      const len = Math.min(Math.max(done - BEAD_STARTS[i], 0), BEAD_LENGTHS[i]);
      mesh.visible = len > 0.001;
      const dx = Math.sign(seg.to[0] - seg.from[0]);
      const dz = Math.sign(seg.to[1] - seg.from[1]);
      mesh.position.set(seg.from[0] + (dx * len) / 2, PART.h / 2 + BEAD_H / 2, seg.from[1] + (dz * len) / 2);
      mesh.scale.set(dx ? len : BEAD_W, 1, dz ? len : BEAD_W);
    });
  });

  return (
    <>
      {BEAD_SEGMENTS.map((_, i) => (
        <mesh key={i} ref={(m) => (meshes.current[i] = m)} visible={false}>
          <boxGeometry args={[1, BEAD_H, 1]} />
          <meshStandardMaterial color={color} roughness={0.25} metalness={0.05} />
        </mesh>
      ))}
    </>
  );
}

const FULL = () => 1;

/** A phone rear housing. Moving parts are positioned by the parent through the forwarded ref. */
export const Part = forwardRef(function Part({ bead = 0, ng = false, position }, ref) {
  const fraction = typeof bead === "function" ? bead : bead >= 1 ? FULL : null;
  return (
    <group ref={ref} position={position}>
      <Housing />
      {fraction && <Bead fraction={fraction} color={ng ? COLORS.ng : COLORS.bead} />}
    </group>
  );
});
