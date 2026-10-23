import { router } from "expo-router";
import type { SourceQuery } from "@/lib/api";

/** Opens the sheet listing exactly the transactions behind a figure, source chip, record or chart bar. */
export function openSource(query: SourceQuery, title?: string) {
  router.push({ pathname: "/source", params: { q: JSON.stringify(query), title: title ?? "" } });
}
