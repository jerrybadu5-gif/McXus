import { useEffect, useState } from "react";
import { api, qs } from "@/lib/api";

/** Look up display names for the user ids in a staff list (one request per list). */
export function useNames(ids: string[]): Record<string, string> {
  const [names, setNames] = useState<Record<string, string>>({});
  const key = [...new Set(ids)].sort().join(",");
  useEffect(() => {
    if (!key) return;
    api.get<Record<string, string>>(`/v1/admin/users/names${qs({ ids: key.split(",") })}`).then(setNames, () => {});
  }, [key]);
  return names;
}
