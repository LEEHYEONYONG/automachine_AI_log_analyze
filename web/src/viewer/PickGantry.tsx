import { useFrame } from "@react-three/fiber";
import { useRef, type ReactNode } from "react";
import { MathUtils, type Group, type Mesh } from "three";
import { COLORS, HEAD_HIGH } from "./layout";

const BEAM_Y = 1.6;
const DAMPING = 14;

interface Props {
  /** Pad position as [z, y], evaluated every frame. */
  target: () => [number, number];
  vacuum: boolean;
  /** Rendered on the pad, e.g. the part being carried. */
  children?: ReactNode;
}

/** Z-axis gantry with a vertical vacuum pick head, used by the loader and unloader. */
export function PickGantry({ target, vacuum, children }: Props) {
  const carriage = useRef<Group>(null);
  const head = useRef<Group>(null);
  const rod = useRef<Mesh>(null);

  useFrame((_, dt) => {
    if (!carriage.current || !head.current || !rod.current) return;
    const [z, y] = target();
    carriage.current.position.z = MathUtils.damp(carriage.current.position.z, z, DAMPING, dt);
    head.current.position.y = MathUtils.damp(head.current.position.y, y, DAMPING, dt);
    const top = BEAM_Y;
    const bottom = head.current.position.y + 0.14;
    rod.current.position.y = (top + bottom) / 2;
    rod.current.scale.y = Math.max(0.01, top - bottom);
  });

  return (
    <group>
      {/* fixed frame: one column at the back with a cantilever beam, so the front stays visible */}
      <mesh position={[0, BEAM_Y / 2, -1.9]} castShadow>
        <boxGeometry args={[0.12, BEAM_Y + 0.15, 0.12]} />
        <meshStandardMaterial color={COLORS.frame} />
      </mesh>
      <mesh position={[0, BEAM_Y + 0.08, -0.8]} castShadow>
        <boxGeometry args={[0.16, 0.14, 2.3]} />
        <meshStandardMaterial color={COLORS.frame} />
      </mesh>

      {/* moving carriage, rod and head */}
      <group ref={carriage}>
        <mesh position={[0, BEAM_Y + 0.08, 0]}>
          <boxGeometry args={[0.26, 0.2, 0.26]} />
          <meshStandardMaterial color={COLORS.steel} metalness={0.6} roughness={0.3} />
        </mesh>
        <mesh ref={rod}>
          <cylinderGeometry args={[0.03, 0.03, 1, 12]} />
          <meshStandardMaterial color={COLORS.steel} metalness={0.7} roughness={0.25} />
        </mesh>
        <group ref={head} position={[0, HEAD_HIGH, 0]}>
          <mesh position={[0, 0.09, 0]} castShadow>
            <boxGeometry args={[0.32, 0.1, 0.2]} />
            <meshStandardMaterial color={COLORS.steel} metalness={0.6} roughness={0.3} />
          </mesh>
          <mesh position={[0, 0.02, 0]}>
            <cylinderGeometry args={[0.07, 0.07, 0.04, 16]} />
            <meshStandardMaterial
              color={vacuum ? COLORS.accent : COLORS.frame}
              emissive={vacuum ? COLORS.accent : "#000000"}
              emissiveIntensity={vacuum ? 0.8 : 0}
            />
          </mesh>
          {children}
        </group>
      </group>
    </group>
  );
}
