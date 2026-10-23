import { Grid, OrbitControls } from "@react-three/drei";
import { useFrame } from "@react-three/fiber";
import { useRef } from "react";
import type { MeshStandardMaterial } from "three";
import type { MachineState } from "../types";
import { BELT_TOP, COLORS } from "./layout";
import { Dispenser3D, Inspection3D, Loader3D, Unloader3D, Vision3D, type StationProps } from "./stations";

const STATION_COMPONENTS: Record<string, (p: StationProps) => JSX.Element> = {
  LOADER: Loader3D,
  VISION: Vision3D,
  DISPENSER: Dispenser3D,
  INSPECTION: Inspection3D,
  UNLOADER: Unloader3D,
};

function TowerLamp({ mode }: { mode: MachineState["mode"] }) {
  const red = useRef<MeshStandardMaterial>(null);
  useFrame(({ clock }) => {
    if (red.current && mode === "ALARM") red.current.emissiveIntensity = Math.sin(clock.elapsedTime * 8) > 0 ? 3 : 0.1;
  });
  const lamps = [
    { y: 2.3, color: COLORS.ng, on: mode === "ALARM", ref: red },
    { y: 2.1, color: COLORS.warn, on: mode === "STOPPED", ref: undefined },
    { y: 1.9, color: COLORS.ok, on: mode === "RUNNING", ref: undefined },
  ];
  return (
    <group position={[-6.5, 0, -1.7]}>
      <mesh position={[0, 0.9, 0]}>
        <cylinderGeometry args={[0.03, 0.03, 1.8, 10]} />
        <meshStandardMaterial color={COLORS.frame} />
      </mesh>
      {lamps.map((l) => (
        <mesh key={l.y} position={[0, l.y, 0]}>
          <cylinderGeometry args={[0.1, 0.1, 0.19, 20]} />
          <meshStandardMaterial
            ref={l.ref}
            color={l.color}
            emissive={l.color}
            emissiveIntensity={l.on ? 3 : 0.08}
            transparent
            opacity={l.on ? 1 : 0.45}
          />
        </mesh>
      ))}
    </group>
  );
}

function Conveyor() {
  return (
    <group>
      <mesh position={[0, BELT_TOP / 2, 0]} receiveShadow>
        <boxGeometry args={[12.6, BELT_TOP, 0.8]} />
        <meshStandardMaterial color={COLORS.belt} roughness={0.9} />
      </mesh>
      {[-0.45, 0.45].map((z) => (
        <mesh key={z} position={[0, BELT_TOP + 0.02, z]} castShadow>
          <boxGeometry args={[12.6, 0.1, 0.06]} />
          <meshStandardMaterial color={COLORS.steel} metalness={0.6} roughness={0.35} />
        </mesh>
      ))}
    </group>
  );
}

export function Scene({ state }: { state: MachineState }) {
  const running = state.mode === "RUNNING" && !state.sim.paused;
  const speed = state.sim.speed;
  return (
    <>
      <color attach="background" args={["#0f1419"]} />
      <hemisphereLight args={["#e8eef5", "#2a323a", 1.4]} />
      <ambientLight intensity={0.35} />
      <directionalLight
        position={[6, 10, 6]}
        intensity={2.2}
        castShadow
        shadow-mapSize={[2048, 2048]}
        shadow-camera-left={-9}
        shadow-camera-right={9}
        shadow-camera-top={6}
        shadow-camera-bottom={-6}
      />

      {/* machine table */}
      <mesh position={[0, -0.3, -0.3]} receiveShadow>
        <boxGeometry args={[13.6, 0.6, 4.6]} />
        <meshStandardMaterial color={COLORS.table} roughness={0.8} />
      </mesh>
      <Grid
        position={[0, -0.6, 0]}
        args={[40, 40]}
        cellColor="#1c242c"
        sectionColor="#26313b"
        fadeDistance={30}
        infiniteGrid
      />

      <Conveyor />
      {state.stations.map((s) => {
        const Comp = STATION_COMPONENTS[s.name];
        return Comp ? <Comp key={s.name} station={s} m={state} running={running} speed={speed} /> : null;
      })}
      <TowerLamp mode={state.mode} />

      <OrbitControls
        makeDefault
        enableDamping
        target={[0, 0.4, -0.3]}
        maxPolarAngle={Math.PI / 2.1}
        minDistance={3}
        maxDistance={22}
      />
    </>
  );
}
