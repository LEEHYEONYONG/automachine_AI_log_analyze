import { Html } from "@react-three/drei";
import { useFrame } from "@react-three/fiber";
import { useRef } from "react";
import type { MeshStandardMaterial } from "three";
import { STATION_LABEL, STATION_STATE_LABEL } from "../labels";
import type { StationView } from "../types";
import { COLORS } from "./layout";

const STATE_COLOR = {
  IDLE: COLORS.idle,
  BUSY: COLORS.ok,
  DONE: COLORS.warn,
  ALARM: COLORS.ng,
};

/** Floor plate coloured by station state, plus a name label at the front edge. */
export function StationBase({ station, x }: { station: StationView; x: number }) {
  const mat = useRef<MeshStandardMaterial>(null);

  useFrame(({ clock }) => {
    if (!mat.current) return;
    const blink = station.state === "ALARM" ? 0.5 + 0.5 * Math.sin(clock.elapsedTime * 8) : 1;
    mat.current.emissiveIntensity = 0.35 * blink;
  });

  return (
    <group position={[x, 0, 0]}>
      <mesh position={[0, 0.004, 0]} receiveShadow>
        <boxGeometry args={[2.1, 0.008, 3.4]} />
        <meshStandardMaterial
          ref={mat}
          color={STATE_COLOR[station.state]}
          emissive={STATE_COLOR[station.state]}
          transparent
          opacity={0.2}
        />
      </mesh>
      <Html position={[0, 0.02, 1.95]} center zIndexRange={[10, 0]}>
        <div className={`label3d st-${station.state}`}>
          <strong>{STATION_LABEL[station.name] ?? station.name}</strong>
          <span>{STATION_STATE_LABEL[station.state]}</span>
        </div>
      </Html>
    </group>
  );
}
