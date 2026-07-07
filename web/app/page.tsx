import { promises as fs } from "fs";
import path from "path";
import DigestView from "../components/Digest";
import type { Digest } from "../lib/types";

export default async function Page() {
  const file = path.join(process.cwd(), "public", "data", "latest.json");
  const digest = JSON.parse(await fs.readFile(file, "utf-8")) as Digest;
  return <DigestView digest={digest} />;
}
