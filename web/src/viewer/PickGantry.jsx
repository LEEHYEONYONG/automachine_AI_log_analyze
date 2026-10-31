import { useFrame } from "@react-three/fiber";
import { useRef } from "react";
import { MathUtils } from "three";
import { COLORS, HEAD_HIGH } from "./layout";
import { Model } from "./Model";

const BEAM_Y = 1.6;
const DAMPING = 14;

/** Cantilever Z-axis gantry with a pneumatic vertical axis and four suction cups. */
export function PickGantry({ target, vacuum, children }) {
  const carriage = useRef(null);
  const head = useRef(null);
  const rod = useRef(null);

  useFrame((_, dt) => {
    if (!carriage.current || !head.current || !rod.current) return;
    const [z, y] = target();
    carriage.current.position.z = MathUtils.damp(carriage.current.position.z, z, DAMPING, dt);
    head.current.position.y = MathUtils.damp(head.current.position.y, y, DAMPING, dt);
    const top = BEAM_Y - 0.32; // bottom of the cylinder body
    const bottom = head.current.position.y + 0.1;
    rod.current.position.y = (top + bottom) / 2;
    rod.current.scale.y = Math.max(0.01, top - bottom);
  });

  const cupGlow = vacuum ? { emissive: COLORS.accent, emissiveIntensity: 0.9 } : {};

  return (
    <group>
      {/* column on a foot plate, cantilever beam with rail, motor and cable chain */}
      <Model name="gantry_fixed" />

      <group ref={carriage}>
        {/* pneumatic cylinder body hanging from the carriage, with its rod */}
        <Model name="gantry_carriage" />
        <mesh ref={rod}>
          <cylinderGeometry args={[0.022, 0.022, 1, 12]} />
          <meshStandardMaterial color={COLORS.steel} metalness={0.95} roughness={0.15} />
        </mesh>

        <group ref={head} position={[0, HEAD_HIGH, 0]}>
          <Model name="gantry_head" />
          {[
            [-0.12, -0.07],
            [0.12, -0.07],
            [-0.12, 0.07],
            [0.12, 0.07],
          ].map(([x, z]) => (
            <mesh key={`${x}${z}`} position={[x, 0.012, z]}>
              <cylinderGeometry args={[0.032, 0.022, 0.024, 16]} />
              <meshStandardMaterial color="#14171b" roughness={0.8} {...cupGlow} />
            </mesh>
          ))}
          {children}
        </group>
      </group>
    </group>
  );
}
