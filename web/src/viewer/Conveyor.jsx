import { tr } from "../prefs";
import { Html } from "@react-three/drei";
import { useFrame } from "@react-three/fiber";
import { useMemo, useRef } from "react";
import { CanvasTexture, MathUtils, RepeatWrapping } from "three";

import { Box, Cyl, Housing, ServoMotor } from "./details";
import {
  BELT_TOP,
  COLORS,
  DOWNSTREAM_X,
  FLOOR_Y,
  LANE_W,
  LANE_Z,
  PART,
  PART_Y,
  STATION_ORDER,
  STATION_SPACING,
  STATION_X,
  UPSTREAM_X,
  ZONE_LEN,
} from "./layout";
import { manualDevice } from "./manual";

const STRIPE = 0.25; // texture repeat length along the belt
const TRANSFER_S = 1.0; // matches the transfer step time on the server
const STOPPER_X = PART.w / 2 + 0.05;

function useBeltTexture() {
  return useMemo(() => {
    const canvas = document.createElement("canvas");
    canvas.width = 64;
    canvas.height = 8;
    const ctx = canvas.getContext("2d");
    ctx.fillStyle = "#171c21";
    ctx.fillRect(0, 0, 64, 8);
    ctx.fillStyle = "#29313a";
    ctx.fillRect(0, 0, 8, 8);
    const texture = new CanvasTexture(canvas);
    texture.wrapS = RepeatWrapping;
    texture.wrapT = RepeatWrapping;
    texture.repeat.set(ZONE_LEN / STRIPE, 1);
    return texture;
  }, []);
}

/** One station's conveyor zone: two edge belts, guide rails, a stopper and a part-present sensor. */
function ConveyorZone({ x, moving, speed, stopperUp = false, partPresent = false, foreign = false }) {
  const texture = useBeltTexture();
  const stopper = useRef(null);
  const belt = useRef(null); // a belt material; both lanes share its texture

  useFrame((_, dt) => {
    if (moving && belt.current) {
      belt.current.map.offset.x -= (Math.min(dt, 0.1) * speed * STATION_SPACING) / TRANSFER_S / STRIPE;
    }
    if (stopper.current) {
      const target = stopperUp ? BELT_TOP + 0.02 : BELT_TOP - 0.07;
      stopper.current.position.y = MathUtils.damp(stopper.current.position.y, target, 18, dt);
    }
  });

  const frame = foreign ? "aluDark" : "alu";
  return (
    <group position={[x, 0, 0]}>
      {[-LANE_Z, LANE_Z].map((z) => (
        <group key={z} position={[0, 0, z]}>
          <Box size={[ZONE_LEN, BELT_TOP - 0.02, LANE_W + 0.03]} position={[0, (BELT_TOP - 0.02) / 2, 0]} mat={frame} />
          <mesh position={[0, BELT_TOP - 0.009, 0]} rotation={[-Math.PI / 2, 0, 0]} receiveShadow>
            <planeGeometry args={[ZONE_LEN - 0.04, LANE_W]} />
            <meshStandardMaterial ref={belt} map={texture} roughness={0.9} />
          </mesh>
          {[-ZONE_LEN / 2 + 0.03, ZONE_LEN / 2 - 0.03].map((px) => (
            <Cyl key={px} r={0.03} h={LANE_W + 0.04} position={[px, BELT_TOP - 0.035, 0]}
              rotation={[Math.PI / 2, 0, 0]} mat="steel" />
          ))}
        </group>
      ))}
      {/* guide rails keep the part between the lanes */}
      {[-1, 1].map((side) => (
        <group key={side}>
          <Box size={[ZONE_LEN, 0.03, 0.012]} position={[0, BELT_TOP + 0.03, side * (PART.d / 2 + 0.03)]} mat="steel" />
          {[-0.8, 0, 0.8].map((px) => (
            <Box key={px} size={[0.02, 0.06, 0.02]} position={[px, BELT_TOP, side * (PART.d / 2 + 0.045)]} mat="aluDark" />
          ))}
        </group>
      ))}
      {/* cross members and the zone drive */}
      {[-ZONE_LEN / 2 + 0.1, ZONE_LEN / 2 - 0.1].map((px) => (
        <Box key={px} size={[0.06, 0.04, 2 * LANE_Z + LANE_W]} position={[px, 0.03, 0]} mat="black" />
      ))}
      <ServoMotor position={[ZONE_LEN / 2 - 0.25, 0.07, -LANE_Z - 0.17]} rotation={[0, Math.PI, 0]} />

      {!foreign && (
        <>
          {/* pneumatic stop pin in front of the part, between the lanes */}
          <Box size={[0.06, 0.12, 0.05]} position={[STOPPER_X, 0.05, 0]} mat="aluDark" />
          <mesh ref={stopper} position={[STOPPER_X, BELT_TOP - 0.07, 0]}>
            <cylinderGeometry args={[0.018, 0.018, 0.1, 12]} />
            <meshStandardMaterial color={COLORS.steel} metalness={0.9} roughness={0.2} />
          </mesh>
          {/* through-beam part sensor on the front rail */}
          <Box size={[0.04, 0.04, 0.03]} position={[0.1, BELT_TOP + 0.05, PART.d / 2 + 0.06]} mat="black" />
          <mesh position={[0.1, BELT_TOP + 0.075, PART.d / 2 + 0.06]}>
            <sphereGeometry args={[0.008, 8, 8]} />
            <meshStandardMaterial
              color={partPresent ? COLORS.ok : "#3a2a1a"}
              emissive={partPresent ? COLORS.ok : "#000000"}
              emissiveIntensity={partPresent ? 3 : 0}
              toneMapped={!partPresent}
            />
          </mesh>
        </>
      )}
    </group>
  );
}

/** End of the previous machine's conveyor (or start of the next one) sticking into this cell. */
function NeighbourConveyor({ x, label, moving, speed, partWaiting }

) {
  const legH = BELT_TOP - 0.02 - FLOOR_Y;
  const away = Math.sign(x) * 0.6;
  return (
    <group>
      <ConveyorZone x={x} moving={moving} speed={speed} foreign />
      {[-LANE_Z, LANE_Z].map((z) => (
        <Box key={z} size={[0.06, legH, 0.06]} position={[x + away, FLOOR_Y + legH / 2, z]} mat="aluDark" />
      ))}
      {partWaiting && (
        <group position={[x, PART_Y, 0]}>
          <Housing />
        </group>
      )}
      <Html position={[x + away, BELT_TOP + 0.35, 0]} center zIndexRange={[10, 0]}>
        <div className="label3d neighbour">{label}</div>
      </Html>
    </group>
  );
}

/** All conveyor zones. Each zone runs only while a part is moving onto or off it. */
export function ConveyorLine({ m, running, speed }) {
  const stations = m.stations;
  const byName = Object.fromEntries(stations.map((s) => [s.name, s]));
  const receiving = (name) => !!name && byName[name]?.step === "TRANSFER_IN";
  const outfeed = byName.OUTFEED;
  const sendingOut = outfeed?.step === "TRANSFER_OUT";
  const infeed = byName.INFEED;

  return (
    <group>
      {STATION_ORDER.map((name, i) => {
        const s = byName[name];
        const next = STATION_ORDER[i + 1];
        const isOutfeed = name === "OUTFEED";
        const belt = manualDevice(m, `${name}_BELT`);
        const stopper = manualDevice(m, `${name}_STOPPER`);
        const moving = belt !== null ? belt >= 1 : running && (receiving(name) || receiving(next) || (isOutfeed && sendingOut));
        const stopperUp =
          stopper !== null
            ? stopper >= 0.5
            : isOutfeed
              ? !["STOPPER_DOWN", "TRANSFER_OUT"].includes(s?.step ?? "")
              : !receiving(next);
        return (
          <ConveyorZone
            key={name}
            x={STATION_X[name]}
            moving={moving}
            speed={speed}
            stopperUp={stopperUp}
            partPresent={!!s?.wp && s.step !== "TRANSFER_IN"}
          />
        );
      })}
      <NeighbourConveyor
        x={UPSTREAM_X}
        label={tr("이전 공정")}
        moving={running && receiving("INFEED")}
        speed={speed}
        partWaiting={!!infeed && !["WAIT_UPSTREAM", "TRANSFER_IN"].includes(infeed.step)}
      />
      <NeighbourConveyor x={DOWNSTREAM_X} label={tr("다음 공정")} moving={running && sendingOut} speed={speed} partWaiting={false} />
    </group>
  );
}
