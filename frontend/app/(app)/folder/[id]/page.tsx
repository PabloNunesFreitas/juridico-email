"use client";
import { useEffect, useState } from "react";
import { useParams } from "next/navigation";
import { api, Folder } from "@/lib/api";
import { DemandView } from "@/components/DemandView";

export default function FolderPage() {
  const params = useParams();
  const folderId = Number(params.id);
  const [folder, setFolder] = useState<Folder | null>(null);

  useEffect(() => {
    api.listFolders().then(all => {
      setFolder(all.find(f => f.id === folderId) ?? null);
    }).catch(() => {});
  }, [folderId]);

  return (
    <DemandView
      source="folder"
      folderId={folderId}
      title={`📁 ${folder?.name ?? "Pasta"}`}
    />
  );
}
