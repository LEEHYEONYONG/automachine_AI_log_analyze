// Small building blocks for the parts that change at runtime. The machine's rigid hardware
// is in the model file (see Model.jsx and web/models/machine.py).
import { RoundedBox } from "@react-three/drei";
import { useMemo } from "react";
import { CatmullRomCurve3, TubeGeometry, Vector3 } from "three";
import { MAX_TRAYS, PART, TRAY_PITCH } from "./layout";

const MATERIALS = {
  alu: { color: "#b9c3cd", metalness: 0.75, roughness: 0.32 },
  aluDark: { color: "#56626e", metalness: 0.6, roughness: 0.4 },
  black: { color: "#1c2127", metalness: 0.25, roughness: 0.55 },
  steel: { color: "#d4dbe2", metalness: 0.95, roughness: 0.18 },
  cabinet: { color: "#a9b2bb", metalness: 0.2, roughness: 0.6 },
  plate: { color: "#2f3740", metalness: 0.5, roughness: 0.45 },
  white: { color: "#e3e7eb", metalness: 0.1, roughness: 0.5 },
};

export function Box({ size, position, rotation, mat = "alu", color }) {
  const m = MATERIALS[mat];
  return (
    <mesh position={position} rotation={rotation} castShadow receiveShadow>
      <boxGeometry args={size} />
      <meshStandardMaterial {...m} color={color ?? m.color} />
    </mesh>
  );
}

export function Cyl({ r, h, position, rotation, mat = "steel", color, rTop, segments = 20 }) {
  const m = MATERIALS[mat];
  return (
    <mesh position={position} rotation={rotation} castShadow>
      <cylinderGeometry args={[rTop ?? r, r, h, segments]} />
      <meshStandardMaterial {...m} color={color ?? m.color} />
    </mesh>
  );
}

/** Flexible hose through the given points. */
export function Hose({ points, radius = 0.015, color = "#8c96a0" }) {
  // Points arrive as fresh array literals each render, so memoise on their contents.
  const key = JSON.stringify(points);
  const geometry = useMemo(
    () => new TubeGeometry(new CatmullRomCurve3(JSON.parse(key).map((p) => new Vector3(...p))), 32, radius, 8, false),
    [key, radius],
  );
  return (
    <mesh geometry={geometry} castShadow>
      <meshStandardMaterial color={color} roughness={0.6} />
    </mesh>
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

/** Stack of black JEDEC-style trays, a part showing on the top one. */
export function TrayStack({ fill }) {
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

/** The syringe parts that change at runtime, inside the head's hardware; the needle tip is at the group origin. */
export function Syringe({ level, valveOpen }) {
  const fill = Math.max(0, Math.min(1, level));
  const fillH = Math.max(0.001, 0.46 * fill);
  return (
    <group>
      <mesh position={[0, 0.005, 0]} visible={valveOpen}>
        <sphereGeometry args={[0.022, 12, 12]} />
        <meshStandardMaterial color="#e8a33d" emissive="#e8a33d" emissiveIntensity={2} />
      </mesh>
      {/* lamp on the valve's front plate, lit while the valve is open */}
      <mesh position={[0, 0.22, 0.087]}>
        <sphereGeometry args={[0.008, 8, 8]} />
        <meshStandardMaterial color="#e8a33d" emissive="#e8a33d" emissiveIntensity={valveOpen ? 4 : 0.1} toneMapped={false} />
      </mesh>
      {/* clear barrel, adhesive, plunger and volume marks */}
      <mesh position={[0, 0.51, 0]}>
        <cylinderGeometry args={[0.07, 0.07, 0.48, 24, 1, true]} />
        <meshPhysicalMaterial color="#e6f0f8" transparent opacity={0.28} roughness={0.05} depthWrite={false} />
      </mesh>
      <Cyl r={0.064} h={fillH} position={[0, 0.28 + fillH / 2, 0]} mat="white" color="#d9952f" />
      <Cyl r={0.066} h={0.025} position={[0, 0.28 + fillH + 0.013, 0]} mat="white" />
      {[0.33, 0.42, 0.51, 0.6, 0.69].map((y) => (
        <Cyl key={y} r={0.0715} h={0.003} position={[0, y, 0]} mat="white" color="#9fb0bf" />
      ))}
      <Hose points={[[0, 0.8, 0], [0, 0.95, 0], [0.04, 1.08, -0.08], [0.06, 1.2, -0.22]]} radius={0.014} />
    </group>
  );
}
