import { useFrame } from "@react-three/fiber";
import { forwardRef, useRef } from "react";
import type { Group, Mesh } from "three";
import { BEAD_LENGTHS, BEAD_SEGMENTS, BEAD_STARTS, BEAD_TOTAL, COLORS, PART } from "./layout";

const BEAD_W = 0.025;
const BEAD_H = 0.014;

/** Adhesive bead drawn up to `fraction()` of its length, updated every frame. */
function Bead({ fraction, color }: { fraction: () => number; color: string }) {
  const meshes = useRef<(Mesh | null)[]>([]);

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
          <meshStandardMaterial color={color} roughness={0.35} />
        </mesh>
      ))}
    </>
  );
}

const FULL = () => 1;

interface PartProps {
  /** 0 = no bead yet, 1 = finished bead; a function lets the dispenser draw it live. */
  bead?: number | (() => number);
  ng?: boolean;
  position?: [number, number, number];
}

/** A phone rear housing. Moving parts are positioned by the parent through the forwarded ref. */
export const Part = forwardRef<Group, PartProps>(function Part({ bead = 0, ng = false, position }, ref) {
  const fraction = typeof bead === "function" ? bead : bead >= 1 ? FULL : null;
  return (
    <group ref={ref} position={position}>
      <mesh castShadow>
        <boxGeometry args={[PART.w, PART.h, PART.d]} />
        <meshStandardMaterial color={COLORS.part} metalness={0.5} roughness={0.35} />
      </mesh>
      {fraction && <Bead fraction={fraction} color={ng ? COLORS.ng : COLORS.bead} />}
    </group>
  );
});
