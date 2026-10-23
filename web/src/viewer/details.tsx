// Small building blocks shared by the stations and the machine frame. Everything is
// built from primitives so the repo needs no 3D model files.
import { RoundedBox } from "@react-three/drei";
import { useMemo } from "react";
import { CatmullRomCurve3, TubeGeometry, Vector3 } from "three";
import { PART } from "./layout";

export const MATERIALS = {
  alu: { color: "#b9c3cd", metalness: 0.75, roughness: 0.32 },
  aluDark: { color: "#56626e", metalness: 0.6, roughness: 0.4 },
  black: { color: "#1c2127", metalness: 0.25, roughness: 0.55 },
  steel: { color: "#d4dbe2", metalness: 0.95, roughness: 0.18 },
  cabinet: { color: "#a9b2bb", metalness: 0.2, roughness: 0.6 },
  plate: { color: "#2f3740", metalness: 0.5, roughness: 0.45 },
  white: { color: "#e3e7eb", metalness: 0.1, roughness: 0.5 },
};
export type MatName = keyof typeof MATERIALS;

type Vec3 = [number, number, number];

interface BoxProps {
  size: Vec3;
  position?: Vec3;
  rotation?: Vec3;
  mat?: MatName;
  color?: string;
}

export function Box({ size, position, rotation, mat = "alu", color }: BoxProps) {
  const m = MATERIALS[mat];
  return (
    <mesh position={position} rotation={rotation} castShadow receiveShadow>
      <boxGeometry args={size} />
      <meshStandardMaterial {...m} color={color ?? m.color} />
    </mesh>
  );
}

interface CylProps {
  r: number;
  h: number;
  position?: Vec3;
  rotation?: Vec3;
  mat?: MatName;
  color?: string;
  rTop?: number;
  segments?: number;
}

export function Cyl({ r, h, position, rotation, mat = "steel", color, rTop, segments = 20 }: CylProps) {
  const m = MATERIALS[mat];
  return (
    <mesh position={position} rotation={rotation} castShadow>
      <cylinderGeometry args={[rTop ?? r, r, h, segments]} />
      <meshStandardMaterial {...m} color={color ?? m.color} />
    </mesh>
  );
}

/** Flexible hose through the given points. */
export function Hose({ points, radius = 0.015, color = "#8c96a0" }: { points: Vec3[]; radius?: number; color?: string }) {
  // Points arrive as fresh array literals each render, so memoise on their contents.
  const key = JSON.stringify(points);
  const geometry = useMemo(
    () => new TubeGeometry(new CatmullRomCurve3(points.map((p) => new Vector3(...p))), 32, radius, 8, false),
    [key, radius],
  );
  return (
    <mesh geometry={geometry} castShadow>
      <meshStandardMaterial color={color} roughness={0.6} />
    </mesh>
  );
}

/** Linear guide rail along x or z. */
export function LinearRail({ length, position, axis = "z" }: { length: number; position: Vec3; axis?: "x" | "z" }) {
  const size: Vec3 = axis === "z" ? [0.05, 0.04, length] : [length, 0.04, 0.05];
  return <Box size={size} position={position} mat="steel" />;
}

/** Servo motor with flange, axis along +z by default. */
export function ServoMotor({ position, rotation }: { position: Vec3; rotation?: Vec3 }) {
  return (
    <group position={position} rotation={rotation}>
      <Box size={[0.15, 0.15, 0.24]} mat="black" />
      <Box size={[0.17, 0.17, 0.03]} position={[0, 0, 0.13]} mat="aluDark" />
      <Box size={[0.05, 0.04, 0.06]} position={[0, 0.09, -0.06]} mat="black" color="#2b3138" />
    </group>
  );
}

/** Energy chain lying on top of an axis. */
export function CableChain({ length, position, axis = "z" }: { length: number; position: Vec3; axis?: "x" | "z" }) {
  const links = Math.max(2, Math.round(length / 0.07));
  return (
    <group position={position}>
      {Array.from({ length: links }, (_, i) => {
        const d = -length / 2 + (i + 0.5) * (length / links);
        return (
          <Box
            key={i}
            size={axis === "z" ? [0.09, 0.05, 0.055] : [0.055, 0.05, 0.09]}
            position={axis === "z" ? [0, 0, d] : [d, 0, 0]}
            mat="black"
          />
        );
      })}
    </group>
  );
}

/** A phone rear housing with a camera bump (no bead; see Part). */
export function Housing() {
  return (
    <group>
      <RoundedBox args={[PART.w, PART.h, PART.d]} radius={0.025} smoothness={3} castShadow>
        <meshStandardMaterial color="#6b7580" metalness={0.75} roughness={0.28} />
      </RoundedBox>
      <RoundedBox args={[0.12, 0.014, 0.12]} radius={0.02} smoothness={2} position={[-0.21, PART.h / 2, -0.07]}>
        <meshStandardMaterial color="#22272d" metalness={0.6} roughness={0.25} />
      </RoundedBox>
      {[-0.03, 0.03].map((dz) => (
        <mesh key={dz} position={[-0.21, PART.h / 2 + 0.008, -0.07 + dz]}>
          <cylinderGeometry args={[0.018, 0.018, 0.006, 16]} />
          <meshStandardMaterial color="#0d1013" metalness={0.9} roughness={0.1} />
        </mesh>
      ))}
    </group>
  );
}

const TRAY_PITCH = 0.065;
export const MAX_TRAYS = 12;

/** Height of the top part surface in a tray stack that is `fill` full (where the pick pad lands). */
export function trayStackTop(fill: number): number {
  const trays = Math.round(Math.max(0, Math.min(1, fill)) * MAX_TRAYS);
  return trays === 0 ? 0.06 : trays * TRAY_PITCH + 0.055;
}

/** Stack of black JEDEC-style trays, a part showing on the top one. */
export function TrayStack({ fill }: { fill: number }) {
  const trays = Math.round(Math.max(0, Math.min(1, fill)) * MAX_TRAYS);
  return (
    <group>
      <Box size={[0.98, 0.03, 0.62]} position={[0, 0.015, 0]} mat="aluDark" />
      {[
        [-0.46, -0.28],
        [0.46, -0.28],
        [-0.46, 0.28],
        [0.46, 0.28],
      ].map(([x, z]) => (
        <Box key={`${x}${z}`} size={[0.04, 0.95, 0.04]} position={[x, 0.475, z]} mat="alu" />
      ))}
      {Array.from({ length: trays }, (_, i) => (
        <Box key={i} size={[0.86, 0.045, 0.5]} position={[0, 0.03 + i * TRAY_PITCH + 0.0225, 0]} mat="black" />
      ))}
      {trays > 0 && (
        <group position={[0, 0.03 + trays * TRAY_PITCH - 0.005, 0]}>
          <Housing />
        </group>
      )}
    </group>
  );
}

/** Syringe barrel on a dispensing valve; the needle tip is at the group origin. */
export function Syringe({ level, valveOpen }: { level: number; valveOpen: boolean }) {
  const fill = Math.max(0, Math.min(1, level));
  const fillH = Math.max(0.001, 0.46 * fill);
  return (
    <group>
      <Cyl r={0.007} h={0.12} position={[0, 0.06, 0]} mat="steel" />
      <Cyl r={0.03} rTop={0.02} h={0.05} position={[0, 0.145, 0]} mat="white" color="#e1709f" />
      <mesh position={[0, 0.005, 0]} visible={valveOpen}>
        <sphereGeometry args={[0.022, 12, 12]} />
        <meshStandardMaterial color="#e8a33d" emissive="#e8a33d" emissiveIntensity={2} />
      </mesh>
      {/* valve body with air port */}
      <Box size={[0.17, 0.1, 0.17]} position={[0, 0.22, 0]} mat="black" />
      <Cyl r={0.018} h={0.06} position={[0.11, 0.22, 0]} rotation={[0, 0, Math.PI / 2]} mat="steel" />
      {/* clear barrel, adhesive, plunger and adapter cap */}
      <mesh position={[0, 0.51, 0]}>
        <cylinderGeometry args={[0.07, 0.07, 0.48, 24, 1, true]} />
        <meshPhysicalMaterial color="#e6f0f8" transparent opacity={0.28} roughness={0.05} depthWrite={false} />
      </mesh>
      <Cyl r={0.064} h={fillH} position={[0, 0.28 + fillH / 2, 0]} mat="white" color="#d9952f" />
      <Cyl r={0.066} h={0.025} position={[0, 0.28 + fillH + 0.013, 0]} mat="white" />
      <Cyl r={0.08} h={0.05} position={[0, 0.775, 0]} mat="black" color="#2f6fc0" />
      <Hose points={[[0, 0.8, 0], [0, 0.95, 0], [0.04, 1.08, -0.08], [0.06, 1.2, -0.22]]} radius={0.014} />
    </group>
  );
}
