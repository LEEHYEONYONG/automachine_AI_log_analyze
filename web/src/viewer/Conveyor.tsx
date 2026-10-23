import { useFrame } from "@react-three/fiber";
import { useMemo } from "react";
import { CanvasTexture, RepeatWrapping } from "three";
import { Box, Cyl, ServoMotor } from "./details";
import { BELT_TOP, STATION_SPACING } from "./layout";

const LENGTH = 12.6;
const STRIPE = 0.3; // texture repeat length along the belt
const TRANSFER_S = 1.0; // matches Station.transfer_s on the server

function useBeltTexture() {
  return useMemo(() => {
    const canvas = document.createElement("canvas");
    canvas.width = 64;
    canvas.height = 16;
    const ctx = canvas.getContext("2d")!;
    ctx.fillStyle = "#171c21";
    ctx.fillRect(0, 0, 64, 16);
    ctx.fillStyle = "#232a31";
    ctx.fillRect(0, 0, 6, 16);
    const texture = new CanvasTexture(canvas);
    texture.wrapS = RepeatWrapping;
    texture.wrapT = RepeatWrapping;
    texture.repeat.set(LENGTH / STRIPE, 1);
    return texture;
  }, []);
}

/** Flat belt conveyor. The belt only moves while a part is being indexed to the next station. */
export function Conveyor({ moving, speed }: { moving: boolean; speed: number }) {
  const texture = useBeltTexture();

  useFrame((_, dt) => {
    if (!moving) return;
    const distance = (Math.min(dt, 0.1) * speed * STATION_SPACING) / TRANSFER_S;
    texture.offset.x -= distance / STRIPE;
  });

  return (
    <group>
      {/* side frames and belt */}
      {[-0.47, 0.47].map((z) => (
        <Box key={z} size={[LENGTH + 0.2, 0.2, 0.06]} position={[0, BELT_TOP - 0.06, z]} mat="alu" />
      ))}
      <Box size={[LENGTH, BELT_TOP - 0.02, 0.86]} position={[0, (BELT_TOP - 0.02) / 2, 0]} mat="black" />
      <mesh position={[0, BELT_TOP + 0.001, 0]} rotation={[-Math.PI / 2, 0, 0]} receiveShadow>
        <planeGeometry args={[LENGTH, 0.86]} />
        <meshStandardMaterial map={texture} roughness={0.9} />
      </mesh>
      {/* end rollers, guide rails, drive motor */}
      {[-LENGTH / 2, LENGTH / 2].map((x) => (
        <Cyl key={x} r={0.075} h={0.9} position={[x, BELT_TOP - 0.075, 0]} rotation={[Math.PI / 2, 0, 0]} mat="steel" />
      ))}
      {[-0.42, 0.42].map((z) => (
        <Box key={z} size={[LENGTH, 0.04, 0.025]} position={[0, BELT_TOP + 0.04, z]} mat="steel" />
      ))}
      <ServoMotor position={[LENGTH / 2 + 0.05, 0.08, -0.62]} rotation={[0, Math.PI, 0]} />
      <Box size={[0.16, 0.12, 0.2]} position={[LENGTH / 2 + 0.05, 0.08, -0.45]} mat="aluDark" />
    </group>
  );
}
