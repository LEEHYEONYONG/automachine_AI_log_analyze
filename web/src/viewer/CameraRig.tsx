import { useFrame, useThree } from "@react-three/fiber";
import { useEffect, useRef } from "react";
import { Vector3 } from "three";
import type { OrbitControls as OrbitControlsImpl } from "three-stdlib";
import { STATION_X } from "./layout";

export const VIEWS = {
  overview: { label: "전체", position: [2.5, 5.8, 13.5], target: [0, 0.3, -0.3] },
  loader: { label: "투입부", position: [STATION_X.LOADER + 1.6, 2.4, 3.6], target: [STATION_X.LOADER, 0.6, -0.7] },
  dispenser: { label: "디스펜서", position: [1.4, 1.3, 2.2], target: [0, 0.35, -0.2] },
  unloader: { label: "배출부", position: [STATION_X.UNLOADER - 1.6, 2.4, 3.6], target: [STATION_X.UNLOADER, 0.5, -0.4] },
} as const;
export type ViewName = keyof typeof VIEWS;

/** Glides the camera to a preset view; the user can orbit freely afterwards. */
export function CameraRig({ view }: { view: ViewName }) {
  const camera = useThree((s) => s.camera);
  const controls = useThree((s) => s.controls) as OrbitControlsImpl | null;
  const goal = useRef<{ pos: Vector3; target: Vector3 } | null>(null);

  useEffect(() => {
    const v = VIEWS[view];
    goal.current = { pos: new Vector3(...v.position), target: new Vector3(...v.target) };
  }, [view]);

  useFrame((_, dt) => {
    if (!goal.current || !controls) return;
    const k = 1 - Math.exp(-6 * dt);
    camera.position.lerp(goal.current.pos, k);
    controls.target.lerp(goal.current.target, k);
    controls.update();
    const arrived =
      camera.position.distanceTo(goal.current.pos) < 0.01 && controls.target.distanceTo(goal.current.target) < 0.01;
    if (arrived) goal.current = null;
  });

  return null;
}
