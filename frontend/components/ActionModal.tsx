"use client";

interface Option {
  value: string;
  label: string;
  description?: string;
}

interface ActionModalProps {
  title: string;
  subtitle?: string;
  options: Option[];
  selected: string;
  onSelect: (value: string) => void;
  confirmLabel: string;
  confirmClassName?: string;
  onConfirm: () => void;
  onCancel: () => void;
  extra?: React.ReactNode;
}

export function ActionModal({
  title,
  subtitle,
  options,
  selected,
  onSelect,
  confirmLabel,
  confirmClassName = "btn-primary",
  onConfirm,
  onCancel,
  extra,
}: ActionModalProps) {
  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center">
      {/* Backdrop */}
      <div className="absolute inset-0 bg-black/40" onClick={onCancel} />

      {/* Card */}
      <div className="relative bg-white rounded-xl shadow-xl w-full max-w-md mx-4 p-6">
        <h2 className="text-base font-semibold text-gray-900">{title}</h2>
        {subtitle && (
          <p className="text-sm text-gray-500 mt-0.5 truncate">{subtitle}</p>
        )}

        <div className="mt-4 space-y-2">
          {options.map((opt) => (
            <label
              key={opt.value}
              className={`flex items-start gap-3 p-3 rounded-lg border cursor-pointer transition-colors ${
                selected === opt.value
                  ? "border-blue-500 bg-blue-50"
                  : "border-gray-200 hover:bg-gray-50"
              }`}
            >
              <input
                type="radio"
                name="modal-option"
                value={opt.value}
                checked={selected === opt.value}
                onChange={() => onSelect(opt.value)}
                className="mt-0.5 accent-blue-600"
              />
              <div>
                <div className="text-sm font-medium text-gray-800">{opt.label}</div>
                {opt.description && (
                  <div className="text-xs text-gray-500 mt-0.5">{opt.description}</div>
                )}
              </div>
            </label>
          ))}
        </div>

        {extra && <div className="mt-3">{extra}</div>}

        <div className="flex justify-end gap-2 mt-5">
          <button className="btn-secondary" onClick={onCancel}>
            Cancelar
          </button>
          <button className={confirmClassName} onClick={onConfirm}>
            {confirmLabel}
          </button>
        </div>
      </div>
    </div>
  );
}
