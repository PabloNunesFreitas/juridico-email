"use client";
import { useEffect, useState } from "react";
import { _registerToastListener } from "@/lib/toast";

interface Item { id: number; msg: string; type: "success" | "error" | "info"; }
let _counter = 0;

export function Toaster() {
  const [items, setItems] = useState<Item[]>([]);

  useEffect(() => {
    _registerToastListener((msg, type) => {
      const id = ++_counter;
      setItems(prev => [...prev.slice(-4), { id, msg, type }]);
      setTimeout(() => setItems(prev => prev.filter(t => t.id !== id)), 4500);
    });
  }, []);

  if (!items.length) return null;
  return (
    <div className="fixed bottom-4 right-4 z-50 flex flex-col gap-2 max-w-sm pointer-events-none">
      {items.map(t => (
        <div
          key={t.id}
          className={`px-4 py-3 rounded-lg shadow-xl text-sm font-medium text-white ${
            t.type === "success" ? "bg-green-600" : t.type === "error" ? "bg-red-600" : "bg-gray-800"
          }`}
        >
          {t.msg}
        </div>
      ))}
    </div>
  );
}
