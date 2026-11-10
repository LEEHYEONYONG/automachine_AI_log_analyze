import { Html } from "@react-three/drei";
import { useFrame } from "@react-three/fiber";
import { useRef } from "react";

import { tr } from "../prefs";
import { DEVICE_LABEL } from "./faults";
import { COLORS } from "./layout";

/** A pulsing red shell around one part with a label, drawn inside that part's group so it follows it. */
export function FaultMarker({ fault, device, radius, position, flat = 1 }) {
  const mat = useRef(null);
  useFrame(({ clock }) => {
    if (mat.current) mat.current.opacity = 0.18 + 0.14 * Math.sin(clock.elapsedTime * 4);
  });
  if (fault?.device !== device) return null;
  return (
    <group position={position}>
      {/* flat < 1 squashes the shell for wide, low parts so it does not hide the workpiece */}
      <mesh renderOrder={10} scale={[1, flat, 1]}>
        <sphereGeometry args={[radius, 24, 16]} />
        <meshBasicMaterial ref={mat} color={COLORS.ng} transparent opacity={0.25} depthWrite={false} toneMapped={false} />
      </mesh>
      <mesh rotation={[Math.PI / 2, 0, 0]}>
        <torusGeometry args={[radius * 1.05, 0.006, 8, 48]} />
        <meshBasicMaterial color={COLORS.ng} toneMapped={false} />
      </mesh>
      <Html position={[0, radius * flat + 0.08, 0]} center zIndexRange={[20, 10]}>
        <div className="label3d fault3d">
          <strong>{DEVICE_LABEL[device]}</strong>
          <span>{fault.alert.started_at ? tr("AI: {a} 의심", { a: fault.alert.cause_label }) : fault.alert.cause_label}</span>
        </div>
      </Html>
    </group>
  );
}
