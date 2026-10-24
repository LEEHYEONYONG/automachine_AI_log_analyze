import { useFrame } from "@react-three/fiber";
import { useRef } from "react";
import { DoubleSide, MathUtils } from "three";

import { Box, CableChain, Cyl, Hose, LinearRail, ServoMotor, Syringe, TrayStack } from "./details";
import {
  BACK_Z,
  BELT_TOP,
  COLORS,
  HEAD_HIGH,
  LANE_W,
  LANE_Z,
  LIFT_H,
  PART,
  PART_TOP,
  PART_Y,
  STATION_SPACING,
  STATION_X,
  beadPoint,
  lerp,
  trayStackTop,
} from "./layout";
import { manualAxis, manualDevice } from "./manual";
import { Part } from "./Part";
import { PickGantry } from "./PickGantry";
import { StationBase } from "./StationBase";
import { useStepClock } from "./stepClock";

const MM = 1 / 200; // scene units per millimetre (a 140 mm housing is 0.7 units long)

/** Steps during which a lift-up unit holds the part up, plus how it moves in and out. */
function liftLevel(step, t, upSteps) {
  if (step === "LIFT_UP") return t;
  if (step === "LIFT_DOWN") return 1 - t;
  if (step === "RESEAT") return 1 - 0.7 * Math.sin(Math.PI * t); // drop and re-seat on the vacuum pads
  return upSteps.includes(step) ? 1 : 0;
}

const plateTop = (level) => lerp(BELT_TOP - 0.025, BELT_TOP + LIFT_H, level);
const liftedPartY = (level) => Math.max(PART_Y, plateTop(level) + PART.h / 2);

/** Air-cylinder lift-up unit between the two belts; optional vacuum cups on the plate. */
function LiftUnit({ level, cups = false, vacuum = false }) {
  const plate = useRef(null);
  useFrame((_, dt) => {
    if (plate.current) plate.current.position.y = MathUtils.damp(plate.current.position.y, plateTop(level()), 20, dt);
  });
  const glow = vacuum ? { emissive: COLORS.accent, emissiveIntensity: 1.2 } : {};
  return (
    <group>
      <Cyl r={0.045} h={0.1} position={[0, 0.05, 0]} mat="alu" />
      <group ref={plate} position={[0, plateTop(0), 0]}>
        <Box size={[0.5, 0.02, 2 * LANE_Z - LANE_W - 0.03]} position={[0, -0.01, 0]} mat="aluDark" />
        <Cyl r={0.015} h={0.12} position={[0, -0.08, 0]} mat="steel" />
        {cups &&
          [-0.15, 0.15].flatMap((x) =>
            [-0.05, 0.05].map((z) => (
              <mesh key={`${x}${z}`} position={[x, 0.002, z]}>
                <cylinderGeometry args={[0.025, 0.02, 0.012, 14]} />
                <meshStandardMaterial color="#14171b" roughness={0.8} {...glow} />
              </mesh>
            )),
          )}
      </group>
    </group>
  );
}

/** Overhead camera column with an arm reaching over the belt. */
function CameraMount({ armY }) {
  return (
    <group>
      <Box size={[0.26, 0.03, 0.26]} position={[0, 0.015, -0.95]} mat="aluDark" />
      <Box size={[0.08, armY + 0.06, 0.08]} position={[0, (armY + 0.06) / 2, -0.95]} />
      <Box size={[0.08, 0.08, 1.0]} position={[0, armY, -0.47]} />
    </group>
  );
}

/** Same pseudo-random skew for a given part id, so a part arrives a little crooked and stays that way. */
function skewOf(id) {
  let h = 0;
  for (const c of id ?? "") h = (h * 31 + c.charCodeAt(0)) | 0;
  const r = (k) => (((h >> k) & 0xff) / 255) * 2 - 1;
  return [r(0) * 0.035, r(8) * 0.025, r(16) * 0.06];
}

// ---------------------------------------------------------------------------

export function Infeed3D({ station, running, speed }) {
  const p = useStepClock(station, running, speed);
  const part = useRef(null);
  const skew = skewOf(station.wp);

  useFrame(() => {
    if (!part.current) return;
    const x = station.step === "TRANSFER_IN" ? lerp(-STATION_SPACING, 0, p()) : 0;
    part.current.position.set(x + skew[0], PART_Y, skew[1]);
    part.current.rotation.y = skew[2];
  });

  const reading = station.step === "ID_READ";
  return (
    <group position={[STATION_X.INFEED, 0, 0]}>
      <StationBase station={station} x={0} />
      {/* 2D code reader on a bracket behind the belt, looking down at the camera-bump corner */}
      <Box size={[0.05, 0.6, 0.05]} position={[-0.2, 0.3, -0.5]} mat="aluDark" />
      <group position={[-0.2, 0.62, -0.38]} rotation={[0.9, 0, 0]}>
        <Box size={[0.12, 0.08, 0.16]} mat="black" />
        <mesh position={[0, -0.04, 0.06]} rotation={[Math.PI / 2, 0, 0]}>
          <planeGeometry args={[0.06, 0.04]} />
          <meshStandardMaterial color={COLORS.ng} emissive={COLORS.ng} emissiveIntensity={reading ? 2 : 0.3}
            side={DoubleSide} />
        </mesh>
      </group>
      {reading && (
        <mesh position={[-0.2, 0.42, -0.24]} rotation={[0.9, 0, 0]}>
          <coneGeometry args={[0.06, 0.45, 16, 1, true]} />
          <meshStandardMaterial color={COLORS.ng} emissive={COLORS.ng} emissiveIntensity={1.5} transparent opacity={0.25}
            depthWrite={false} toneMapped={false} />
        </mesh>
      )}
      {station.wp && <Part ref={part} />}
    </group>
  );
}

export function Vision3D({ station, m, running, speed }) {
  const p = useStepClock(station, running, speed);
  const part = useRef(null);
  const pusherX = useRef(null);
  const pusherZ = useRef(null);
  const skew = skewOf(station.wp);

  const upSteps = ["PUSH_ALIGN", "SETTLE", "CAPTURE", "PROCESS", "RELEASE"];
  const level = () => manualDevice(m, "VISION_LIFT") ?? liftLevel(station.step, p(), upSteps);
  const push = () => {
    const t = p();
    if (station.step === "PUSH_ALIGN") return t;
    if (station.step === "RELEASE") return 1 - t;
    return ["SETTLE", "CAPTURE", "PROCESS"].includes(station.step) ? 1 : 0;
  };
  // Once pushed against the datum pins the part stays aligned until it leaves.
  const aligned = ["SETTLE", "CAPTURE", "PROCESS", "RELEASE", "LIFT_DOWN"].includes(station.step) || station.state === "DONE";

  useFrame((_, dt) => {
    const kx = manualDevice(m, "VISION_PUSH_X") ?? push();
    const kz = manualDevice(m, "VISION_PUSH_Y") ?? push();
    if (part.current) {
      const manual = m.op_mode === "MANUAL";
      const left = manual ? 1 - Math.min(kx, kz) : aligned ? 0 : 1 - (station.step === "PUSH_ALIGN" ? kx : 0);
      const x = station.step === "TRANSFER_IN" ? lerp(-STATION_SPACING, 0, p()) : 0;
      part.current.position.set(x + skew[0] * left, liftedPartY(level()), skew[1] * left);
      part.current.rotation.y = skew[2] * left;
    }
    // pusher pads travel from parked to touching the part's edge
    if (pusherX.current) pusherX.current.position.x = MathUtils.damp(pusherX.current.position.x, lerp(-0.62, -PART.w / 2 - 0.015, kx), 20, dt);
    if (pusherZ.current) pusherZ.current.position.z = MathUtils.damp(pusherZ.current.position.z, lerp(0.5, PART.d / 2 + 0.015, kz), 20, dt);
  });

  const capture = station.step === "CAPTURE";
  const padY = BELT_TOP + LIFT_H + PART.h / 2;
  const pinsUp = level() > 0.5;

  return (
    <group position={[STATION_X.VISION, 0, 0]}>
      <StationBase station={station} x={0} />
      <LiftUnit level={level} />
      {/* datum pins (right end and back edge) rise with the lift */}
      {[
        [PART.w / 2 + 0.02, 0.08],
        [PART.w / 2 + 0.02, -0.08],
        [-0.15, -PART.d / 2 - 0.02],
        [0.15, -PART.d / 2 - 0.02],
      ].map(([x, z]) => (
        <Cyl key={`${x}${z}`} r={0.012} h={0.08} position={[x, pinsUp ? padY : BELT_TOP - 0.03, z]} mat="steel" />
      ))}
      {/* end pusher (pushes +x) and side pusher (pushes -z) */}
      <Box size={[0.18, 0.06, 0.06]} position={[-0.86, padY, 0]} mat="alu" />
      <group ref={pusherX} position={[-0.62, padY, 0]}>
        <Cyl r={0.01} h={0.25} position={[-0.125, 0, 0]} rotation={[0, 0, Math.PI / 2]} mat="steel" />
        <Box size={[0.02, 0.04, 0.12]} mat="white" color="#e6c34a" />
      </group>
      <Box size={[0.06, 0.06, 0.18]} position={[0, padY, 0.74]} mat="alu" />
      <group ref={pusherZ} position={[0, padY, 0.5]}>
        <Cyl r={0.01} h={0.25} position={[0, 0, 0.125]} rotation={[Math.PI / 2, 0, 0]} mat="steel" />
        <Box size={[0.2, 0.04, 0.02]} mat="white" color="#e6c34a" />
      </group>

      <CameraMount armY={1.6} />
      <Box size={[0.16, 0.24, 0.16]} position={[0, 1.42, 0]} mat="black" />
      <Box size={[0.17, 0.02, 0.17]} position={[0, 1.55, 0]} mat="aluDark" />
      <Cyl r={0.055} h={0.14} position={[0, 1.23, 0]} mat="black" color="#0d1013" />
      <Cyl r={0.06} h={0.02} position={[0, 1.17, 0]} mat="steel" />
      <Hose points={[[0.06, 1.5, 0], [0.12, 1.62, -0.1], [0.08, 1.66, -0.5], [0.05, 1.5, -0.9]]} radius={0.012} />
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

export function Dispenser3D({ station, m, running, speed }) {
  const p = useStepClock(station, running, speed);
  const part = useRef(null);
  const bridge = useRef(null);
  const carriage = useRef(null);
  const head = useRef(null);
  const rod = useRef(null);

  const BEAM_Y = 1.85;
  const HOME_Y = 0.75;
  const WORK_Y = PART_TOP + LIFT_H + 0.05; // the part is lifted onto the vacuum fixture
  const SCALE_TOP = 0.2;
  const SCALE_X = 0.75; // beside the belt so it does not hide the head from the default camera
  const SCALE_Z = -1.0;
  const [sx, sz] = beadPoint(0);

  const upSteps = ["VACUUM_ON", "APPROACH", "HEIGHT_MEASURE", "DISPENSE", "DWELL", "RETRACT", "VACUUM_OFF"];
  const level = () => manualDevice(m, "DISP_LIFT") ?? liftLevel(station.step, p(), upSteps);

  // [x, z, y] of the needle tip relative to the station
  const target = () => {
    const mx = manualAxis(m, "DISP_X");
    if (mx !== null) {
      return [mx * MM, (manualAxis(m, "DISP_Y") ?? 0) * MM, WORK_Y + (manualAxis(m, "DISP_Z") ?? 88) * MM];
    }
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
    if (part.current) {
      const x = station.step === "TRANSFER_IN" ? lerp(-STATION_SPACING, 0, p()) : 0;
      part.current.position.set(x, liftedPartY(level()), 0);
    }
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
      : ["DWELL", "RETRACT", "VACUUM_OFF", "LIFT_DOWN"].includes(station.step) || station.state === "DONE"
        ? 1
        : 0;

  return (
    <group position={[STATION_X.DISPENSER, 0, 0]}>
      <StationBase station={station} x={0} />
      <LiftUnit level={level} cups vacuum={(manualDevice(m, "DISP_FIXTURE_VAC") ?? 0) >= 1 || m.fixture_vacuum_on} />

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
          <mesh key={i} position={g.pos }>
            <boxGeometry args={g.size } />
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

export function Inspection3D({ station, m, running, speed }) {
  const p = useStepClock(station, running, speed);
  const part = useRef(null);
  const scanner = useRef(null);
  const SCAN_FROM = -0.42;
  const SCAN_TO = 0.42;

  useFrame((_, dt) => {
    const t = p();
    if (part.current) {
      const x = station.step === "TRANSFER_IN" ? lerp(-STATION_SPACING, 0, t) : 0;
      part.current.position.set(x, PART_Y, 0);
    }
    if (scanner.current) {
      const manual = manualAxis(m, "SCAN_X");
      const goal =
        manual !== null
          ? manual * MM
          : station.step === "SCAN"
            ? lerp(SCAN_FROM, SCAN_TO, t)
            : station.step === "SCAN_RETURN"
              ? lerp(SCAN_TO, SCAN_FROM, t)
              : SCAN_FROM;
      scanner.current.position.x = MathUtils.damp(scanner.current.position.x, goal, 25, dt);
    }
  });

  const scanning = station.step === "SCAN";
  const judged = station.judge === "OK" || station.judge === "NG";
  const lampColor = !judged ? COLORS.idle : station.judge === "OK" ? COLORS.ok : COLORS.ng;

  return (
    <group position={[STATION_X.INSPECTION, 0, 0]}>
      <StationBase station={station} x={0} />
      <CameraMount armY={1.55} />
      {/* short scan axis across the part; camera and line laser ride on it */}
      <Box size={[1.2, 0.08, 0.1]} position={[0, 1.47, 0]} mat="alu" />
      <LinearRail length={1.1} position={[0, 1.42, 0.06]} axis="x" />
      <ServoMotor position={[0.68, 1.47, 0]} rotation={[0, Math.PI / 2, 0]} />
      <group ref={scanner} position={[SCAN_FROM, 0, 0]}>
        <Box size={[0.2, 0.06, 0.18]} position={[0, 1.39, 0]} mat="aluDark" />
        <Box size={[0.14, 0.18, 0.16]} position={[0, 1.27, 0]} mat="black" />
        <Cyl r={0.045} h={0.1} position={[0, 1.13, 0]} mat="black" color="#0d1013" />
        <mesh position={[0.05, 1.27, 0.081]}>
          <sphereGeometry args={[0.018, 16, 16]} />
          <meshStandardMaterial color={lampColor} emissive={lampColor} emissiveIntensity={judged ? 2 : 0.2} />
        </mesh>
        <group position={[0.16, 1.2, 0]} rotation={[0, 0, 0.35]}>
          <Box size={[0.05, 0.16, 0.07]} mat="black" />
        </group>
        {scanning && (
          <mesh position={[0, PART_TOP + 0.02, 0]}>
            <boxGeometry args={[0.012, 0.004, 0.5]} />
            <meshStandardMaterial color={COLORS.ng} emissive={COLORS.ng} emissiveIntensity={4} toneMapped={false} />
          </mesh>
        )}
      </group>
      {station.wp && <Part ref={part} bead={1} ng={station.judge === "NG"} />}
    </group>
  );
}

export function Outfeed3D({ station, m, running, speed }) {
  const p = useStepClock(station, running, speed);
  const beltPart = useRef(null);
  const fill = m.ng_buffer / m.ng_buffer_capacity;
  const bufferTop = trayStackTop(fill);
  const carrying = !!station.wp && ["PICK_UP", "MOVE_TO_NG", "PLACE"].includes(station.step);
  const placed = station.step === "RETURN";

  const target = () => {
    const my = manualAxis(m, "NG_PICK_Y");
    if (my !== null) {
      const low = my > 200 ? bufferTop + PART.h : PART_TOP;
      return [-my * MM, lerp(HEAD_HIGH, low, manualDevice(m, "NG_PICK_Z") ?? 0)];
    }
    const t = p();
    switch (station.step) {
      case "PICK_DOWN":
        return [0, lerp(HEAD_HIGH, PART_TOP, t)];
      case "VACUUM_ON":
        return [0, PART_TOP];
      case "PICK_UP":
        return [0, lerp(PART_TOP, HEAD_HIGH, t)];
      case "MOVE_TO_NG":
        return [lerp(0, BACK_Z, t), HEAD_HIGH];
      case "PLACE":
        return [BACK_Z, lerp(HEAD_HIGH, bufferTop + PART.h, t)];
      case "RETURN":
        return [lerp(BACK_Z, 0, t), HEAD_HIGH];
      default:
        return [0, HEAD_HIGH];
    }
  };

  useFrame(() => {
    if (!beltPart.current) return;
    const t = p();
    const x =
      station.step === "TRANSFER_IN" ? lerp(-STATION_SPACING, 0, t) : station.step === "TRANSFER_OUT" ? lerp(0, STATION_SPACING, t) : 0;
    beltPart.current.position.set(x, PART_Y, 0);
  });

  return (
    <group position={[STATION_X.OUTFEED, 0, 0]}>
      <StationBase station={station} x={0} />
      {/* NG buffer drawer behind the belt */}
      <group position={[0, 0, BACK_Z]}>
        <TrayStack fill={fill} />
        <Box size={[1.06, 0.06, 0.7]} position={[0, -0.0, 0]} mat="white" color="#b9262d" />
        <Box size={[0.3, 0.03, 0.03]} position={[0, 0.03, 0.37]} mat="steel" />
      </group>
      <PickGantry target={target} vacuum={(manualDevice(m, "NG_PICK_VAC") ?? 0) >= 1 || m.ng_picker_vacuum_on}>
        {carrying && <Part position={[0, -PART.h / 2, 0]} bead={1} ng />}
      </PickGantry>
      {station.wp && !carrying && !placed && <Part ref={beltPart} bead={1} ng={station.judge === "NG"} />}
    </group>
  );
}
