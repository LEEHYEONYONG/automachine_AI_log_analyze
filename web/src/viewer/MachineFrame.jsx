import { MeshReflectorMaterial } from "@react-three/drei";
import { useFrame } from "@react-three/fiber";
import { useRef } from "react";
import { DoubleSide, MathUtils } from "three";

import { Box, Cyl } from "./details";
import { COLORS, FLOOR_Y, FRAME } from "./layout";
import { Model } from "./Model";

const P = 0.08; // aluminium profile size
const W = FRAME.x * 2;
const D = FRAME.zFront - FRAME.zBack;
const ZC = (FRAME.zFront + FRAME.zBack) / 2;
const H = FRAME.height;

/** Factory floor with a yellow safety line around the machine. */
export function Floor({ reflective }) {
  const line = (size, pos) => (
    <mesh rotation={[-Math.PI / 2, 0, 0]} position={[pos[0], FLOOR_Y + 0.002, pos[1]]}>
      <planeGeometry args={size} />
      <meshStandardMaterial color="#d4a72c" roughness={0.8} />
    </mesh>
  );
  const x = FRAME.x + 0.8;
  const z0 = FRAME.zBack - 0.7;
  const z1 = FRAME.zFront + 1.1;
  return (
    <group>
      <mesh rotation={[-Math.PI / 2, 0, 0]} position={[0, FLOOR_Y, 0]} receiveShadow>
        <planeGeometry args={[60, 60]} />
        {reflective ? (
          <MeshReflectorMaterial
            color="#1d2328"
            roughness={0.6}
            metalness={0.6}
            mirror={0.4}
            blur={[200, 80]}
            mixBlur={1}
            mixStrength={1.5}
            resolution={1024}
          />
        ) : (
          <meshStandardMaterial color="#1d2328" roughness={0.95} />
        )}
      </mesh>
      {line([2 * x, 0.08], [0, z0])}
      {line([2 * x, 0.08], [0, z1])}
      {line([0.08, z1 - z0], [-x, (z0 + z1) / 2])}
      {line([0.08, z1 - z0], [x, (z0 + z1) / 2])}
    </group>
  );
}

/** Base cabinet with doors, feet, the table plate and an E-stop. */
export function BaseCabinet({ estop }) {
  const bodyH = -0.06 - (FLOOR_Y + 0.12);
  const bodyY = FLOOR_Y + 0.12 + bodyH / 2;
  return (
    <group>
      <Model name="frame_base" />
      {/* emergency stop on the front, right of the doors */}
      <group position={[6.55, bodyY + 0.25, FRAME.zFront]}>
        {/* the mushroom head sits lower and glows while pressed */}
        <mesh position={[0, 0, estop ? 0.08 : 0.1]} rotation={[Math.PI / 2, 0, 0]}>
          <cylinderGeometry args={[0.07, 0.075, 0.05, 20]} />
          <meshStandardMaterial color="#c8262e" emissive="#ff2a2a" emissiveIntensity={estop ? 2.5 : 0} />
        </mesh>
      </group>
    </group>
  );
}

/** Aluminium profile frame with polycarbonate guards (guards can be hidden). */
/** One half of the front guard, hinged at the outer post; it swings outwards when opened. */
function GuardDoor({ side, open, visible }) {
  const hinge = useRef(null);
  useFrame((_, dt) => {
    if (hinge.current) hinge.current.rotation.y = MathUtils.damp(hinge.current.rotation.y, open ? side * 1.2 : 0, 6, dt);
  });
  const w = W / 2 - 0.02;
  const h = H - 0.9;
  return (
    <group ref={hinge} position={[side * FRAME.x, 0.9, FRAME.zFront]} visible={visible || open}>
      <group position={[-side * (w / 2), h / 2, 0]}>
        <Guard size={[w, h, 0.01]} position={[0, 0, 0]} />
        {/* door frame and handle so an open door reads clearly */}
        <Box size={[w, 0.04, 0.03]} position={[0, h / 2, 0]} mat={open ? "white" : "alu"} color={open ? "#e2b521" : undefined} />
        <Box size={[w, 0.04, 0.03]} position={[0, -h / 2, 0]} mat={open ? "white" : "alu"} color={open ? "#e2b521" : undefined} />
        <Box size={[0.04, h, 0.03]} position={[-side * (w / 2), 0, 0]} mat="alu" />
        <Box size={[0.03, 0.25, 0.05]} position={[-side * (w / 2 - 0.08), 0, 0.04]} mat="steel" />
      </group>
    </group>
  );
}

export function Enclosure({ covers, doorsOpen }) {
  return (
    <group>
      <Model name="frame_posts" />
      {covers && (
        <group>
          <Guard size={[W, H, 0.01]} position={[0, H / 2, FRAME.zBack]} />
          {/* side guards stop above the conveyor openings to the neighbouring machines */}
          <Guard size={[0.01, H - 0.45, D]} position={[-FRAME.x, 0.45 + (H - 0.45) / 2, ZC]} />
          <Guard size={[0.01, H - 0.45, D]} position={[FRAME.x, 0.45 + (H - 0.45) / 2, ZC]} />
          <Guard size={[W, 0.01, D]} position={[0, H, ZC]} />
          <Model name="frame_front_rail" />
        </group>
      )}
      <GuardDoor side={-1} open={!!doorsOpen.FRONT_LEFT} visible={covers} />
      <GuardDoor side={1} open={!!doorsOpen.FRONT_RIGHT} visible={covers} />
    </group>
  );
}

/** LED bars under the roof, so the stations are lit from inside the enclosure. */
export function InteriorLights() {
  return (
    <group>
      {[-4.5, 0, 4.5].map((x) => (
        <group key={x} position={[x, H - 0.08, ZC]}>
          <mesh>
            <boxGeometry args={[3.4, 0.03, 0.12]} />
            <meshStandardMaterial color="#ffffff" emissive="#eef4ff" emissiveIntensity={2.5} toneMapped={false} />
          </mesh>
          <pointLight position={[0, -0.1, 0]} intensity={14} distance={9} color="#f4f7ff" />
        </group>
      ))}
    </group>
  );
}

function Guard({ size, position }) {
  return (
    <mesh position={position}>
      <boxGeometry args={size} />
      <meshPhysicalMaterial
        color="#d6e6f5"
        transparent
        opacity={0.045}
        roughness={0.05}
        metalness={0}
        depthWrite={false}
        side={DoubleSide}
      />
    </mesh>
  );
}

const MODE_SCREEN = {
  RUNNING: "#1f6b45",
  STOPPED: "#6b5a1f",
  ALARM: "#7a1f24",
};

/** Swing-arm HMI touch panel at the front right; the screen tint follows the machine mode. */
export function HmiPendant({ mode }) {
  return (
    <group position={[FRAME.x - 0.6, 0, FRAME.zFront + 0.25]}>
      <Model name="hmi_pendant" />
      <group position={[0, 1.55, 0.05]} rotation={[-0.25, -0.3, 0]}>
        <mesh position={[0, 0, 0.033]}>
          <planeGeometry args={[0.54, 0.36]} />
          <meshStandardMaterial color={MODE_SCREEN[mode]} emissive={MODE_SCREEN[mode]} emissiveIntensity={0.9} />
        </mesh>
      </group>
    </group>
  );
}

/** Three-colour signal tower on the top frame. */
export function SignalTower({ mode }) {
  const red = useRef(null);
  useFrame(({ clock }) => {
    if (red.current && mode === "ALARM") red.current.emissiveIntensity = Math.sin(clock.elapsedTime * 8) > 0 ? 3 : 0.1;
  });
  const lamps = [
    { y: 0.62, color: COLORS.ng, on: mode === "ALARM", ref: red },
    { y: 0.44, color: COLORS.warn, on: mode === "STOPPED", ref: undefined },
    { y: 0.26, color: COLORS.ok, on: mode === "RUNNING", ref: undefined },
  ];
  return (
    <group position={[-FRAME.x + 0.25, H + P / 2, FRAME.zBack + 0.25]}>
      <Model name="signal_tower" />
      {lamps.map((l) => (
        <group key={l.y} position={[0, l.y, 0]}>
          <mesh>
            <cylinderGeometry args={[0.075, 0.075, 0.16, 24]} />
            <meshStandardMaterial
              ref={l.ref}
              color={l.color}
              emissive={l.color}
              emissiveIntensity={l.on ? 3 : 0.05}
              transparent
              opacity={l.on ? 1 : 0.5}
            />
          </mesh>
          <Cyl r={0.077} h={0.02} position={[0, -0.09, 0]} mat="white" />
        </group>
      ))}
    </group>
  );
}
