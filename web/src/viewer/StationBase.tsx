import { Html } from "@react-three/drei";
import { useFrame } from "@react-three/fiber";
import { useRef } from "react";
import type { MeshStandardMaterial } from "three";
import { STATION_LABEL, STATION_STATE_LABEL } from "../labels";
import type { StationView } from "../types";
import { BELT_TOP, COLORS } from "./layout";

const STATE_COLOR = {
  IDLE: COLORS.idle,
  BUSY: COLORS.ok,
  DONE: COLORS.warn,
  ALARM: COLORS.ng,
};

/** Status LED strip on the conveyor's front rail plus a name label at the front edge. */
export function StationBase({ station, x }: { station: StationView; x: number }) {
  const mat = useRef<MeshStandardMaterial>(null);

  useFrame(({ clock }) => {
    if (!mat.current) return;
    const blink = station.state === "ALARM" ? 0.5 + 0.5 * Math.sin(clock.elapsedTime * 8) : 1;
    mat.current.emissiveIntensity = (station.state === "IDLE" ? 0.4 : 1.6) * blink;
  });

  return (
    <group position={[x, 0, 0]}>
      <mesh position={[0, BELT_TOP - 0.06, 0.505]}>
        <boxGeometry args={[1.6, 0.05, 0.01]} />
        <meshStandardMaterial
          ref={mat}
          color={STATE_COLOR[station.state]}
          emissive={STATE_COLOR[station.state]}
          toneMapped={false}
        />
      </mesh>
      <Html position={[0, 0.02, 1.7]} center zIndexRange={[10, 0]}>
        <div className={`label3d st-${station.state}`}>
          <strong>{STATION_LABEL[station.name] ?? station.name}</strong>
          <span>{STATION_STATE_LABEL[station.state]}</span>
        </div>
      </Html>
    </group>
  );
}
