import { promises as fs } from "fs";
import path from "path";
import DigestClient from "../components/DigestClient";
import type { Digest } from "../lib/types";

export default async function Page() {
  const file = path.join(process.cwd(), "public", "data", "latest.json");
  const digest = JSON.parse(await fs.readFile(file, "utf-8")) as Digest;
  return <DigestClient digest={digest} />;
}
