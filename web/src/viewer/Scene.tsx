import { Environment, Lightformer, OrbitControls } from "@react-three/drei";
import type { MachineState } from "../types";
import { CameraRig, VIEWS, type ViewName } from "./CameraRig";
import { ConveyorLine } from "./Conveyor";
import { BaseCabinet, Enclosure, Floor, HmiPendant, SignalTower } from "./MachineFrame";
import { Dispenser3D, Infeed3D, Inspection3D, Outfeed3D, Vision3D, type StationProps } from "./stations";

const STATION_COMPONENTS: Record<string, (p: StationProps) => JSX.Element> = {
  INFEED: Infeed3D,
  VISION: Vision3D,
  DISPENSER: Dispenser3D,
  INSPECTION: Inspection3D,
  OUTFEED: Outfeed3D,
};

/** Soft factory-style reflections generated in the scene, so nothing is downloaded. */
function FactoryLighting() {
  return (
    <Environment resolution={256} frames={1}>
      <Lightformer intensity={2.2} position={[0, 6, 0]} rotation-x={Math.PI / 2} scale={[14, 4, 1]} />
      <Lightformer intensity={1.2} position={[0, 3, 8]} scale={[16, 2, 1]} />
      <Lightformer intensity={0.8} position={[-9, 2, 0]} rotation-y={Math.PI / 2} scale={[8, 2, 1]} />
      <Lightformer intensity={0.8} position={[9, 2, 0]} rotation-y={-Math.PI / 2} scale={[8, 2, 1]} />
    </Environment>
  );
}

export function Scene({ state, covers, view }: { state: MachineState; covers: boolean; view: ViewName }) {
  const running = state.mode === "RUNNING" && !state.sim.paused;
  const speed = state.sim.speed;
  return (
    <>
      <color attach="background" args={["#0f1419"]} />
      <fog attach="fog" args={["#0f1419", 22, 45]} />
      <FactoryLighting />
      <hemisphereLight args={["#e8eef5", "#2a323a", 0.5]} />
      <directionalLight
        position={[6, 12, 7]}
        intensity={1.8}
        castShadow
        shadow-mapSize={[2048, 2048]}
        shadow-bias={-0.0005}
        shadow-camera-left={-10}
        shadow-camera-right={10}
        shadow-camera-top={8}
        shadow-camera-bottom={-8}
      />

      <Floor />
      <BaseCabinet estop={state.safety.estop} />
      <Enclosure covers={covers} doorsOpen={state.safety.doors_open} />
      <ConveyorLine m={state} running={running} speed={speed} />
      {state.stations.map((s) => {
        const Comp = STATION_COMPONENTS[s.name];
        return Comp ? <Comp key={s.name} station={s} m={state} running={running} speed={speed} /> : null;
      })}
      <SignalTower mode={state.mode} />
      <HmiPendant mode={state.mode} />

      <OrbitControls
        makeDefault
        enableDamping
        target={[...VIEWS.overview.target]}
        maxPolarAngle={Math.PI / 2.05}
        minDistance={1.2}
        maxDistance={24}
      />
      <CameraRig view={view} />
    </>
  );
}
