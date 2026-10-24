import { useFrame, useThree } from "@react-three/fiber";
import { useEffect, useRef } from "react";
import { Vector3 } from "three";

import { VIEWS } from "./layout";

/** Glides the camera to a preset view; the user can orbit freely afterwards. */
export function CameraRig({ view }) {
  const camera = useThree((s) => s.camera);
  const controls = useThree((s) => s.controls) ;
  const goal = useRef(null);

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
