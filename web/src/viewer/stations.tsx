import { useFrame } from "@react-three/fiber";
import { useRef } from "react";
import { DoubleSide, MathUtils, type Group, type Mesh } from "three";
import type { MachineState, StationView } from "../types";
import { Box, CableChain, Cyl, Hose, LinearRail, ServoMotor, Syringe, TrayStack, trayStackTop } from "./details";
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

/** Profile column behind the belt with an arm reaching over it, for overhead cameras. */
function CameraMount({ armY }: { armY: number }) {
  return (
    <group>
      <Box size={[0.26, 0.03, 0.26]} position={[0, 0.015, -0.95]} mat="aluDark" />
      <Box size={[0.08, armY + 0.06, 0.08]} position={[0, (armY + 0.06) / 2, -0.95]} />
      <Box size={[0.08, 0.08, 1.0]} position={[0, armY, -0.47]} />
    </group>
  );
}

// ---------------------------------------------------------------------------

export function Loader3D({ station, m, running, speed }: StationProps) {
  const p = useStepClock(station, running, speed);
  const fill = m.magazine / m.magazine_capacity;
  const magTop = trayStackTop(fill);
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
      <group position={[0, 0, BACK_Z]}>
        <TrayStack fill={fill} />
      </group>
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
      <CameraMount armY={1.6} />
      {/* area camera with lens */}
      <Box size={[0.16, 0.24, 0.16]} position={[0, 1.42, 0]} mat="black" />
      <Box size={[0.17, 0.02, 0.17]} position={[0, 1.55, 0]} mat="aluDark" />
      <Cyl r={0.055} h={0.14} position={[0, 1.23, 0]} mat="black" color="#0d1013" />
      <Cyl r={0.06} h={0.02} position={[0, 1.17, 0]} mat="steel" />
      <Hose points={[[0.06, 1.5, 0], [0.12, 1.62, -0.1], [0.08, 1.66, -0.5], [0.05, 1.5, -0.9]]} radius={0.012} />
      {/* ring light: housing and LED ring */}
      <Box size={[0.04, 0.48, 0.04]} position={[0.32, 1.0, 0]} mat="aluDark" />
      <mesh position={[0, 0.78, 0]} rotation={[Math.PI / 2, 0, 0]}>
        <torusGeometry args={[0.3, 0.035, 12, 48]} />
        <meshStandardMaterial color="#1c2127" metalness={0.3} roughness={0.5} />
      </mesh>
      <mesh position={[0, 0.745, 0]} rotation={[Math.PI / 2, 0, 0]}>
        <torusGeometry args={[0.3, 0.012, 8, 48]} />
        <meshStandardMaterial
          color={capture ? "#ffffff" : "#5a6672"}
          emissive={capture ? "#d8ecff" : "#000000"}
          emissiveIntensity={capture ? 4 : 0}
          toneMapped={!capture}
        />
      </mesh>
      {capture && <pointLight position={[0, 0.65, 0]} intensity={3} distance={1.5} color="#d8ecff" />}
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

  const BEAM_Y = 1.85;
  const HOME_Y = 0.75;
  const WORK_Y = PART_TOP + 0.05;
  const SCALE_TOP = 0.2;
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
        return [SCALE_X, SCALE_Z, SCALE_TOP + 0.06];
      case "WEIGH":
        return [SCALE_X, SCALE_Z, lerp(SCALE_TOP + 0.06, HOME_Y, t)];
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
    const top = BEAM_Y - 0.12;
    const bottom = head.current.position.y + 0.28;
    rod.current.position.y = (top + bottom) / 2;
    rod.current.scale.y = Math.max(0.01, top - bottom);
  });

  const bead = () =>
    station.step === "DISPENSE"
      ? p()
      : station.step === "DWELL" || station.step === "RETRACT" || station.state === "DONE"
        ? 1
        : 0;

  return (
    <group position={[STATION_X.DISPENSER, 0, 0]}>
      <StationBase station={station} x={0} />

      {/* dispensing controller with its air line */}
      <group position={[-0.8, 0, -2.2]}>
        <Box size={[0.7, 0.32, 0.4]} position={[0, 0.16, 0]} mat="white" color="#d5dade" />
        <mesh position={[-0.12, 0.2, 0.201]}>
          <planeGeometry args={[0.3, 0.1]} />
          <meshStandardMaterial color="#0c1a12" emissive={COLORS.ok} emissiveIntensity={0.7} />
        </mesh>
        {[0.12, 0.22].map((x) => (
          <Cyl key={x} r={0.025} h={0.03} position={[x, 0.2, 0.215]} rotation={[Math.PI / 2, 0, 0]} mat="black" />
        ))}
        <Hose points={[[0.3, 0.3, 0], [0.55, 0.45, 0.1], [0.75, 0.6, 0.25]]} radius={0.015} />
      </group>

      {/* weigh scale with a draft shield */}
      <group position={[SCALE_X, 0, SCALE_Z]}>
        <Box size={[0.42, 0.12, 0.38]} position={[0, 0.06, 0]} mat="white" color="#cfd5db" />
        <Cyl r={0.11} h={0.015} position={[0, SCALE_TOP - 0.06, 0]} mat="steel" />
        {[
          { size: [0.36, 0.2, 0.005], pos: [0, 0.22, -0.16] },
          { size: [0.005, 0.2, 0.32], pos: [-0.18, 0.22, 0] },
          { size: [0.005, 0.2, 0.32], pos: [0.18, 0.22, 0] },
        ].map((g, i) => (
          <mesh key={i} position={g.pos as [number, number, number]}>
            <boxGeometry args={g.size as [number, number, number]} />
            <meshPhysicalMaterial color="#d6e6f5" transparent opacity={0.18} depthWrite={false} side={DoubleSide} />
          </mesh>
        ))}
        <mesh position={[0, 0.07, 0.191]}>
          <planeGeometry args={[0.22, 0.06]} />
          <meshStandardMaterial color="#0c1a12" emissive={COLORS.ok} emissiveIntensity={0.7} />
        </mesh>
      </group>

      {/* X axis on the table, then the bridge, its Z carriage and the vertical head */}
      <LinearRail length={1.4} position={[0, 0.02, -1.9]} axis="x" />
      <ServoMotor position={[-0.85, 0.08, -1.9]} rotation={[0, -Math.PI / 2, 0]} />
      <group ref={bridge}>
        <Box size={[0.3, 0.08, 0.3]} position={[0, 0.06, -1.9]} mat="aluDark" />
        <Box size={[0.14, BEAM_Y, 0.14]} position={[0, BEAM_Y / 2 + 0.1, -1.9]} />
        <Box size={[0.18, 0.16, 2.35]} position={[0, BEAM_Y, -0.8]} />
        <LinearRail length={2.2} position={[0.11, BEAM_Y, -0.8]} />
        <ServoMotor position={[0, BEAM_Y, -2.1]} rotation={[0, Math.PI, 0]} />
        <CableChain length={1.3} position={[-0.03, BEAM_Y + 0.11, -1.25]} />
        <group ref={carriage}>
          <Box size={[0.3, 0.24, 0.3]} position={[0, BEAM_Y, 0]} mat="aluDark" />
          <ServoMotor position={[0, BEAM_Y + 0.2, -0.12]} rotation={[-Math.PI / 2, 0, 0]} />
          <mesh ref={rod} position={[0, 1, -0.12]}>
            <boxGeometry args={[0.07, 1, 0.07]} />
            <meshStandardMaterial color={COLORS.steel} metalness={0.8} roughness={0.25} />
          </mesh>
          <group ref={head} position={[0, HOME_Y, 0]}>
            <Box size={[0.08, 0.14, 0.12]} position={[0, 0.24, -0.1]} mat="aluDark" />
            <Syringe level={m.syringe_level_pct / 100} valveOpen={m.dispenser_valve_open} />
            {/* laser height sensor */}
            <Box size={[0.07, 0.13, 0.08]} position={[0.14, 0.2, 0]} mat="black" />
            <mesh position={[0.14, 0.13, 0]} rotation={[Math.PI / 2, 0, 0]}>
              <planeGeometry args={[0.04, 0.04]} />
              <meshStandardMaterial color={COLORS.ng} emissive={COLORS.ng} emissiveIntensity={1} side={DoubleSide} />
            </mesh>
            {station.step === "HEIGHT_MEASURE" && (
              <mesh position={[0.14, 0.06, 0]}>
                <cylinderGeometry args={[0.004, 0.004, 0.13, 6]} />
                <meshStandardMaterial color={COLORS.ng} emissive={COLORS.ng} emissiveIntensity={3} toneMapped={false} />
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

  const scanning = station.step === "SCAN";
  const judged = station.judge === "OK" || station.judge === "NG";
  const lampColor = !judged ? COLORS.idle : station.judge === "OK" ? COLORS.ok : COLORS.ng;

  return (
    <group position={[STATION_X.INSPECTION, 0, 0]}>
      <StationBase station={station} x={0} />
      <CameraMount armY={1.55} />
      {/* line-scan camera */}
      <Box size={[0.2, 0.18, 0.18]} position={[0, 1.36, 0]} mat="black" />
      <Box size={[0.22, 0.02, 0.2]} position={[0, 1.46, 0]} mat="aluDark" />
      <Cyl r={0.05} h={0.12} position={[0, 1.21, 0]} mat="black" color="#0d1013" />
      <Cyl r={0.055} h={0.02} position={[0, 1.15, 0]} mat="steel" />
      <mesh position={[0.07, 1.36, 0.091]}>
        <sphereGeometry args={[0.022, 16, 16]} />
        <meshStandardMaterial color={lampColor} emissive={lampColor} emissiveIntensity={judged ? 2 : 0.2} />
      </mesh>
      {/* line laser, angled down onto the part */}
      <group position={[0.42, 0.75, 0]} rotation={[0, 0, 0.6]}>
        <Box size={[0.06, 0.2, 0.08]} mat="black" />
        <Box size={[0.03, 0.04, 0.06]} position={[0, 0.12, 0]} mat="aluDark" />
      </group>
      <Box size={[0.04, 0.75, 0.04]} position={[0.5, 0.375, -0.2]} mat="aluDark" />
      {scanning && (
        <mesh ref={line} position={[0, PART_TOP + 0.02, 0]}>
          <boxGeometry args={[0.012, 0.004, 0.5]} />
          <meshStandardMaterial color={COLORS.ng} emissive={COLORS.ng} emissiveIntensity={4} toneMapped={false} />
        </mesh>
      )}
      {station.wp && <Part ref={part} bead={1} ng={station.judge === "NG"} />}
    </group>
  );
}

export function Unloader3D({ station, m, running, speed }: StationProps) {
  const p = useStepClock(station, running, speed);
  const beltPart = useRef<Group>(null);
  const fill = m.tray_count / m.tray_capacity;
  const trayTop = trayStackTop(fill);
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
      <group position={[0, 0, BACK_Z]}>
        <TrayStack fill={fill} />
      </group>
      {/* reject chute with side walls, and the NG bin */}
      <group position={[0, 0.12, 0.85]} rotation={[0.35, 0, 0]}>
        <Box size={[0.8, 0.015, 0.55]} mat="steel" />
        {[-0.4, 0.4].map((x) => (
          <Box key={x} size={[0.015, 0.08, 0.55]} position={[x, 0.04, 0]} mat="steel" />
        ))}
      </group>
      <Box size={[0.9, 0.2, 0.42]} position={[0, 0.1, 1.32]} mat="white" color="#b9262d" />
      <Box size={[0.92, 0.03, 0.44]} position={[0, 0.205, 1.32]} mat="white" color="#e2b521" />
      <PickGantry target={target} vacuum={carrying}>
        {carrying && <Part position={[0, -PART.h / 2, 0]} bead={1} />}
      </PickGantry>
      {station.wp && !carrying && <Part ref={beltPart} bead={1} ng={station.judge === "NG"} />}
    </group>
  );
}
