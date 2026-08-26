import type { BoletinProgress } from "@/types/api";
import { wsBase, getToken } from "./api";

type OnEvent = (e: BoletinProgress) => void;
type OnError = (e: Event) => void;

export function watchBoletinProgress(
  id: number,
  onEvent: OnEvent,
  onError: OnError = () => {},
): () => void {
  const token = getToken();
  const url = `${wsBase()}/api/boletines/ws/${id}${token ? `?token=${token}` : ""}`;
  const ws = new WebSocket(url);

  ws.onmessage = (e) => {
    try {
      onEvent(JSON.parse(e.data) as BoletinProgress);
    } catch {
      // ignore malformed messages
    }
  };
  ws.onerror = onError;
  ws.onclose = () => {};

  return () => ws.close();
}
