import { useFrame } from "@react-three/fiber";
import { useRef } from "react";
import { MathUtils, type Group, type Mesh } from "three";
import type { MachineState, StationView } from "../types";
import {
  BACK_Z,
  COLORS,
  HEAD_HIGH,
  PART,
  PART_TOP,
  PART_Y,
  STATION_SPACING,
  STATION_X,
  beadPoint,
  lerp,
} from "./layout";
import { Part } from "./Part";
import { PickGantry } from "./PickGantry";
import { StationBase } from "./StationBase";
import { useStepClock } from "./stepClock";

export interface StationProps {
  station: StationView;
  m: MachineState;
  running: boolean;
  speed: number;
}

/** Parts slide in from the previous station during TRANSFER_IN and then sit at the station centre. */
function usePartOnBelt(station: StationView, progress: () => number) {
  const ref = useRef<Group>(null);
  useFrame(() => {
    if (!ref.current) return;
    const x = station.step === "TRANSFER_IN" ? lerp(-STATION_SPACING, 0, progress()) : 0;
    ref.current.position.set(x, PART_Y, 0);
  });
  return ref;
}

function Post({ z, height }: { z: number; height: number }) {
  return (
    <mesh position={[0, height / 2, z]} castShadow>
      <boxGeometry args={[0.1, height, 0.1]} />
      <meshStandardMaterial color={COLORS.frame} />
    </mesh>
  );
}

/** Stack of housings whose height follows how full it is. */
function Stack({ z, fill, color }: { z: number; fill: number; color: string }) {
  const h = 0.06 + 0.8 * fill;
  return (
    <group position={[0, 0, z]}>
      <mesh position={[0, h / 2, 0]} castShadow>
        <boxGeometry args={[PART.w, h, PART.d]} />
        <meshStandardMaterial color={color} metalness={0.4} roughness={0.5} />
      </mesh>
      {[
        [-0.4, -0.23],
        [0.4, -0.23],
        [-0.4, 0.23],
        [0.4, 0.23],
      ].map(([px, pz]) => (
        <mesh key={`${px}${pz}`} position={[px, 0.5, pz]}>
          <boxGeometry args={[0.04, 1, 0.04]} />
          <meshStandardMaterial color={COLORS.frame} />
        </mesh>
      ))}
    </group>
  );
}

// ---------------------------------------------------------------------------

export function Loader3D({ station, m, running, speed }: StationProps) {
  const p = useStepClock(station, running, speed);
  const magTop = 0.06 + 0.8 * (m.magazine / m.magazine_capacity);
  const carrying = !!station.wp && ["PICK_UP", "MOVE_TO_PLACE", "PLACE"].includes(station.step);

  const target = (): [number, number] => {
    const t = p();
    switch (station.step) {
      case "MOVE_TO_PICK":
        return [lerp(0, BACK_Z, t), HEAD_HIGH];
      case "PICK_DOWN":
        return [BACK_Z, lerp(HEAD_HIGH, magTop, t)];
      case "VACUUM_ON":
        return [BACK_Z, magTop];
      case "PICK_UP":
        return [BACK_Z, lerp(magTop, HEAD_HIGH, t)];
      case "MOVE_TO_PLACE":
        return [lerp(BACK_Z, 0, t), HEAD_HIGH];
      case "PLACE":
        return [0, lerp(HEAD_HIGH, PART_TOP, t)];
      default:
        return [0, HEAD_HIGH];
    }
  };

  return (
    <group position={[STATION_X.LOADER, 0, 0]}>
      <StationBase station={station} x={0} />
      <Stack z={BACK_Z} fill={m.magazine / m.magazine_capacity} color="#8d98a3" />
      <PickGantry target={target} vacuum={m.loader_vacuum_on}>
        {carrying && <Part position={[0, -PART.h / 2, 0]} />}
      </PickGantry>
      {station.wp && !carrying && <Part position={[0, PART_Y, 0]} />}
    </group>
  );
}

export function Vision3D({ station, running, speed }: StationProps) {
  const p = useStepClock(station, running, speed);
  const part = usePartOnBelt(station, p);
  const capture = station.step === "CAPTURE";

  return (
    <group position={[STATION_X.VISION, 0, 0]}>
      <StationBase station={station} x={0} />
      <Post z={-0.95} height={1.6} />
      <mesh position={[0, 1.55, -0.45]}>
        <boxGeometry args={[0.1, 0.1, 1.0]} />
        <meshStandardMaterial color={COLORS.frame} />
      </mesh>
      <mesh position={[0, 1.32, 0]} castShadow>
        <boxGeometry args={[0.22, 0.36, 0.22]} />
        <meshStandardMaterial color="#20262d" metalness={0.3} roughness={0.5} />
      </mesh>
      <mesh position={[0, 1.1, 0]} rotation={[Math.PI / 2, 0, 0]}>
        <cylinderGeometry args={[0.07, 0.09, 0.1, 20]} />
        <meshStandardMaterial color="#0b0e11" />
      </mesh>
      <mesh position={[0, 0.75, 0]} rotation={[Math.PI / 2, 0, 0]}>
        <torusGeometry args={[0.3, 0.025, 12, 48]} />
        <meshStandardMaterial
          color={capture ? "#ffffff" : COLORS.steel}
          emissive={capture ? "#cfe6ff" : "#000000"}
          emissiveIntensity={capture ? 3 : 0}
        />
      </mesh>
      {capture && <pointLight position={[0, 0.7, 0]} intensity={2} distance={1.5} color="#cfe6ff" />}
      {station.wp && <Part ref={part} />}
    </group>
  );
}

export function Dispenser3D({ station, m, running, speed }: StationProps) {
  const p = useStepClock(station, running, speed);
  const part = usePartOnBelt(station, p);
  const bridge = useRef<Group>(null);
  const carriage = useRef<Group>(null);
  const head = useRef<Group>(null);
  const rod = useRef<Mesh>(null);

  const HOME_Y = 0.9;
  const WORK_Y = PART_TOP + 0.05;
  const SCALE_TOP = 0.35;
  const SCALE_X = 0.75; // beside the belt so it does not hide the head from the default camera
  const SCALE_Z = -1.0;
  const [sx, sz] = beadPoint(0);

  // [x, z, y] of the needle tip relative to the station
  const target = (): [number, number, number] => {
    const t = p();
    switch (station.step) {
      case "APPROACH":
        return [lerp(0, sx, t), lerp(0, sz, t), lerp(HOME_Y, WORK_Y, t)];
      case "HEIGHT_MEASURE":
        return [sx, sz, WORK_Y];
      case "DISPENSE": {
        const [x, z] = beadPoint(t);
        return [x, z, WORK_Y];
      }
      case "DWELL":
        return [sx, sz, WORK_Y];
      case "RETRACT":
        return [sx, sz, lerp(WORK_Y, HOME_Y, t)];
      case "MOVE_TO_SCALE":
        return [lerp(0, SCALE_X, t), lerp(0, SCALE_Z, t), HOME_Y];
      case "TEST_SHOT":
        return [SCALE_X, SCALE_Z, SCALE_TOP + 0.05];
      case "WEIGH":
        return [SCALE_X, SCALE_Z, lerp(SCALE_TOP + 0.05, HOME_Y, t)];
      case "MOVE_FROM_SCALE":
        return [lerp(SCALE_X, 0, t), lerp(SCALE_Z, 0, t), HOME_Y];
      default:
        return [0, 0, HOME_Y];
    }
  };

  useFrame((_, dt) => {
    if (!bridge.current || !carriage.current || !head.current || !rod.current) return;
    const [x, z, y] = target();
    bridge.current.position.x = MathUtils.damp(bridge.current.position.x, x, 16, dt);
    carriage.current.position.z = MathUtils.damp(carriage.current.position.z, z, 16, dt);
    head.current.position.y = MathUtils.damp(head.current.position.y, y, 16, dt);
    const bottom = head.current.position.y + 0.8;
    rod.current.position.y = (1.75 + bottom) / 2;
    rod.current.scale.y = Math.max(0.01, 1.75 - bottom);
  });

  const bead = () =>
    station.step === "DISPENSE"
      ? p()
      : station.step === "DWELL" || station.step === "RETRACT" || station.state === "DONE"
        ? 1
        : 0;
  const level = Math.max(0, m.syringe_level_pct) / 100;
  const valveOpen = m.dispenser_valve_open;

  return (
    <group position={[STATION_X.DISPENSER, 0, 0]}>
      <StationBase station={station} x={0} />

      {/* weigh scale behind the belt */}
      <mesh position={[SCALE_X, SCALE_TOP / 2, SCALE_Z]} castShadow>
        <boxGeometry args={[0.5, SCALE_TOP, 0.42]} />
        <meshStandardMaterial color="#3a4450" />
      </mesh>
      <mesh position={[SCALE_X, SCALE_TOP + 0.01, SCALE_Z]}>
        <cylinderGeometry args={[0.14, 0.14, 0.02, 24]} />
        <meshStandardMaterial color={COLORS.steel} metalness={0.7} roughness={0.3} />
      </mesh>
      <mesh position={[SCALE_X, SCALE_TOP * 0.55, SCALE_Z + 0.215]}>
        <planeGeometry args={[0.3, 0.1]} />
        <meshStandardMaterial color="#0c1a12" emissive={COLORS.ok} emissiveIntensity={0.6} />
      </mesh>

      {/* X-moving bridge with a Z carriage and a Z-axis syringe head */}
      <group ref={bridge}>
        <mesh position={[0, 0.95, -1.9]} castShadow>
          <boxGeometry args={[0.14, 1.9, 0.14]} />
          <meshStandardMaterial color={COLORS.frame} />
        </mesh>
        <mesh position={[0, 1.85, -0.8]} castShadow>
          <boxGeometry args={[0.18, 0.16, 2.35]} />
          <meshStandardMaterial color={COLORS.frame} />
        </mesh>
        <group ref={carriage}>
          <mesh position={[0, 1.85, 0]}>
            <boxGeometry args={[0.3, 0.24, 0.3]} />
            <meshStandardMaterial color={COLORS.steel} metalness={0.6} roughness={0.3} />
          </mesh>
          <mesh ref={rod}>
            <boxGeometry args={[0.06, 1, 0.06]} />
            <meshStandardMaterial color={COLORS.steel} metalness={0.7} roughness={0.25} />
          </mesh>
          <group ref={head} position={[0, HOME_Y, 0]}>
            {/* needle (tip at y = 0) */}
            <mesh position={[0, 0.06, 0]} rotation={[Math.PI, 0, 0]}>
              <coneGeometry args={[0.018, 0.12, 12]} />
              <meshStandardMaterial color={COLORS.steel} metalness={0.8} roughness={0.2} />
            </mesh>
            <mesh position={[0, 0.01, 0]} visible={valveOpen}>
              <sphereGeometry args={[0.025, 12, 12]} />
              <meshStandardMaterial color={COLORS.bead} emissive={COLORS.bead} emissiveIntensity={2} />
            </mesh>
            {/* valve body */}
            <mesh position={[0, 0.17, 0]} castShadow>
              <boxGeometry args={[0.18, 0.1, 0.18]} />
              <meshStandardMaterial color="#2b3440" metalness={0.4} />
            </mesh>
            {/* syringe barrel with adhesive level */}
            <mesh position={[0, 0.47, 0]}>
              <cylinderGeometry args={[0.07, 0.07, 0.5, 20]} />
              <meshStandardMaterial color="#cfe0ef" transparent opacity={0.25} />
            </mesh>
            <mesh position={[0, 0.23 + (0.48 * level) / 2, 0]} visible={level > 0.005}>
              <cylinderGeometry args={[0.058, 0.058, Math.max(0.001, 0.48 * level), 20]} />
              <meshStandardMaterial color={COLORS.bead} roughness={0.4} />
            </mesh>
            {/* laser height sensor */}
            <mesh position={[0.13, 0.17, 0]}>
              <boxGeometry args={[0.07, 0.12, 0.07]} />
              <meshStandardMaterial color="#20262d" />
            </mesh>
            {station.step === "HEIGHT_MEASURE" && (
              <mesh position={[0.13, 0.05, 0]}>
                <cylinderGeometry args={[0.004, 0.004, 0.14, 6]} />
                <meshStandardMaterial color={COLORS.ng} emissive={COLORS.ng} emissiveIntensity={3} />
              </mesh>
            )}
          </group>
        </group>
      </group>

      {station.wp && <Part ref={part} bead={bead} />}
    </group>
  );
}

export function Inspection3D({ station, running, speed }: StationProps) {
  const p = useStepClock(station, running, speed);
  const part = usePartOnBelt(station, p);
  const line = useRef<Mesh>(null);

  useFrame(() => {
    if (line.current) line.current.position.x = lerp(-0.38, 0.38, p());
  });

  const judged = station.judge === "OK" || station.judge === "NG";
  const lampColor = !judged ? COLORS.idle : station.judge === "OK" ? COLORS.ok : COLORS.ng;

  return (
    <group position={[STATION_X.INSPECTION, 0, 0]}>
      <StationBase station={station} x={0} />
      <Post z={-0.95} height={1.6} />
      <mesh position={[0, 1.55, -0.45]}>
        <boxGeometry args={[0.1, 0.1, 1.0]} />
        <meshStandardMaterial color={COLORS.frame} />
      </mesh>
      <mesh position={[0, 1.3, 0]} castShadow>
        <boxGeometry args={[0.5, 0.18, 0.2]} />
        <meshStandardMaterial color="#20262d" metalness={0.3} roughness={0.5} />
      </mesh>
      <mesh position={[0.18, 1.3, 0.105]}>
        <sphereGeometry args={[0.035, 16, 16]} />
        <meshStandardMaterial color={lampColor} emissive={lampColor} emissiveIntensity={judged ? 2 : 0.2} />
      </mesh>
      {station.step === "SCAN" && (
        <mesh ref={line} position={[0, PART_TOP + 0.02, 0]}>
          <boxGeometry args={[0.012, 0.004, 0.5]} />
          <meshStandardMaterial color={COLORS.ng} emissive={COLORS.ng} emissiveIntensity={4} />
        </mesh>
      )}
      {station.wp && <Part ref={part} bead={1} ng={station.judge === "NG"} />}
    </group>
  );
}

export function Unloader3D({ station, m, running, speed }: StationProps) {
  const p = useStepClock(station, running, speed);
  const beltPart = useRef<Group>(null);
  const trayTop = 0.06 + 0.8 * (m.tray_count / m.tray_capacity);
  const carrying = !!station.wp && ["MOVE_TO_TRAY", "PLACE"].includes(station.step);

  const target = (): [number, number] => {
    const t = p();
    switch (station.step) {
      case "PICK":
        return [0, lerp(HEAD_HIGH, PART_TOP, t)];
      case "MOVE_TO_TRAY":
        return [lerp(0, BACK_Z, t), HEAD_HIGH];
      case "PLACE":
        return [BACK_Z, lerp(HEAD_HIGH, trayTop + PART.h, t)];
      default:
        return [0, HEAD_HIGH];
    }
  };

  useFrame(() => {
    if (!beltPart.current) return;
    const t = p();
    if (station.step === "TRANSFER_IN") {
      beltPart.current.position.set(lerp(-STATION_SPACING, 0, t), PART_Y, 0);
      beltPart.current.rotation.x = 0;
    } else if (station.step === "NG_CHUTE") {
      // pushed off the front of the belt into the reject chute
      beltPart.current.position.set(0, lerp(PART_Y, 0.08, t), lerp(0, 1.15, t));
      beltPart.current.rotation.x = lerp(0, 0.35, t);
    } else {
      beltPart.current.position.set(0, PART_Y, 0);
      beltPart.current.rotation.x = 0;
    }
  });

  return (
    <group position={[STATION_X.UNLOADER, 0, 0]}>
      <StationBase station={station} x={0} />
      <Stack z={BACK_Z} fill={m.tray_count / m.tray_capacity} color="#9aa59a" />
      {/* reject chute and bin in front of the belt */}
      <mesh position={[0, 0.12, 0.9]} rotation={[0.35, 0, 0]}>
        <boxGeometry args={[0.8, 0.02, 0.5]} />
        <meshStandardMaterial color={COLORS.frame} />
      </mesh>
      <mesh position={[0, 0.08, 1.3]}>
        <boxGeometry args={[0.85, 0.16, 0.4]} />
        <meshStandardMaterial color={COLORS.ng} transparent opacity={0.55} />
      </mesh>
      <PickGantry target={target} vacuum={carrying}>
        {carrying && <Part position={[0, -PART.h / 2, 0]} bead={1} />}
      </PickGantry>
      {station.wp && !carrying && <Part ref={beltPart} bead={1} ng={station.judge === "NG"} />}
    </group>
  );
}
