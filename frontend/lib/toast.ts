type ToastType = "success" | "error" | "info";
type Listener = (msg: string, type: ToastType) => void;

let listener: Listener | null = null;

export function toast(msg: string, type: ToastType = "info") {
  listener?.(msg, type);
}

export function _registerToastListener(fn: Listener) {
  listener = fn;
}
