import { useFrame } from "@react-three/fiber";
import { useRef, type ReactNode } from "react";
import { MathUtils, type Group, type Mesh } from "three";
import { Box, CableChain, Cyl, LinearRail, ServoMotor } from "./details";
import { COLORS, HEAD_HIGH } from "./layout";

const BEAM_Y = 1.6;
const COLUMN_Z = -1.9;
const DAMPING = 14;

interface Props {
  /** Pad position as [z, y], evaluated every frame. */
  target: () => [number, number];
  vacuum: boolean;
  /** Rendered under the pad, e.g. the part being carried. */
  children?: ReactNode;
}

/** Cantilever Z-axis gantry with a pneumatic vertical axis and four suction cups. */
export function PickGantry({ target, vacuum, children }: Props) {
  const carriage = useRef<Group>(null);
  const head = useRef<Group>(null);
  const rod = useRef<Mesh>(null);

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
      <Box size={[0.32, 0.03, 0.32]} position={[0, 0.015, COLUMN_Z]} mat="aluDark" />
      <Box size={[0.12, BEAM_Y + 0.12, 0.12]} position={[0, (BEAM_Y + 0.12) / 2, COLUMN_Z]} mat="alu" />
      <Box size={[0.16, 0.14, 2.35]} position={[0, BEAM_Y + 0.08, -0.78]} mat="alu" />
      <LinearRail length={2.2} position={[0.1, BEAM_Y + 0.06, -0.78]} />
      <ServoMotor position={[0, BEAM_Y + 0.08, COLUMN_Z - 0.2]} rotation={[0, Math.PI, 0]} />
      <CableChain length={1.2} position={[-0.03, BEAM_Y + 0.18, -1.3]} />

      <group ref={carriage}>
        <Box size={[0.28, 0.22, 0.24]} position={[0, BEAM_Y + 0.07, 0]} mat="aluDark" />
        {/* pneumatic cylinder body hanging from the carriage, with its rod */}
        <Cyl r={0.055} h={0.34} position={[0, BEAM_Y - 0.15, 0]} mat="alu" />
        <Cyl r={0.06} h={0.03} position={[0, BEAM_Y - 0.31, 0]} mat="aluDark" />
        <mesh ref={rod}>
          <cylinderGeometry args={[0.022, 0.022, 1, 12]} />
          <meshStandardMaterial color={COLORS.steel} metalness={0.95} roughness={0.15} />
        </mesh>

        <group ref={head} position={[0, HEAD_HIGH, 0]}>
          <Box size={[0.36, 0.035, 0.24]} position={[0, 0.085, 0]} mat="alu" />
          <Box size={[0.1, 0.06, 0.1]} position={[0, 0.125, 0]} mat="aluDark" />
          {[
            [-0.12, -0.07],
            [0.12, -0.07],
            [-0.12, 0.07],
            [0.12, 0.07],
          ].map(([x, z]) => (
            <group key={`${x}${z}`} position={[x, 0, z]}>
              <Cyl r={0.008} h={0.05} position={[0, 0.045, 0]} mat="steel" />
              <mesh position={[0, 0.012, 0]}>
                <cylinderGeometry args={[0.032, 0.022, 0.024, 16]} />
                <meshStandardMaterial color="#14171b" roughness={0.8} {...cupGlow} />
              </mesh>
            </group>
          ))}
          {children}
        </group>
      </group>
    </group>
  );
}
