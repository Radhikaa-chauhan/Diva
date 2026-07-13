"use client";

import React, { useState, useRef } from "react";

type UploadZoneProps = {
  onFileSelect: (file: File | null) => void;
  selectedFile: File | null;
  previewUrl: string | null;
  maxSizeMB: number;
};

export default function UploadZone({
  onFileSelect,
  selectedFile,
  previewUrl,
  maxSizeMB,
}: UploadZoneProps) {
  const [isDragActive, setIsDragActive] = useState(false);
  const fileInputRef = useRef<HTMLInputElement>(null);

  const handleDrag = (e: React.DragEvent) => {
    e.preventDefault();
    e.stopPropagation();
    if (e.type === "dragenter" || e.type === "dragover") {
      setIsDragActive(true);
    } else if (e.type === "dragleave") {
      setIsDragActive(false);
    }
  };

  const handleDrop = (e: React.DragEvent) => {
    e.preventDefault();
    e.stopPropagation();
    setIsDragActive(false);

    if (e.dataTransfer.files && e.dataTransfer.files[0]) {
      const file = e.dataTransfer.files[0];
      if (validateFile(file)) {
        onFileSelect(file);
      }
    }
  };

  const handleFileChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    if (e.target.files && e.target.files[0]) {
      const file = e.target.files[0];
      if (validateFile(file)) {
        onFileSelect(file);
      }
    }
  };

  const validateFile = (file: File): boolean => {
    const validTypes = ["image/jpeg", "image/png", "image/webp"];
    if (!validTypes.includes(file.type)) {
      alert("Unsupported file format. Please upload JPEG, PNG, or WEBP.");
      return false;
    }
    if (file.size > maxSizeMB * 1024 * 1024) {
      alert(`File is too large. Max size is ${maxSizeMB}MB.`);
      return false;
    }
    return true;
  };

  const triggerInput = () => {
    fileInputRef.current?.click();
  };

  return (
    <div className="w-full">
      {!previewUrl ? (
        <div
          onDragEnter={handleDrag}
          onDragOver={handleDrag}
          onDragLeave={handleDrag}
          onDrop={handleDrop}
          onClick={triggerInput}
          className={`flex flex-col items-center justify-center border-2 border-dashed rounded-xl p-8 text-center cursor-pointer transition-all duration-300 ${
            isDragActive
              ? "border-purple-500 bg-purple-950/20 shadow-[0_0_15px_rgba(168,85,247,0.25)]"
              : "border-zinc-800 bg-zinc-900/40 hover:border-zinc-700 hover:bg-zinc-900/60"
          }`}
        >
          <input
            ref={fileInputRef}
            type="file"
            accept="image/jpeg,image/png,image/webp"
            className="hidden"
            onChange={handleFileChange}
          />
          
          <div className="flex h-12 w-12 items-center justify-center rounded-full bg-purple-950/50 border border-purple-800/40 text-purple-400 mb-4 shadow-inner">
            <svg
              className="h-6 w-6"
              fill="none"
              viewBox="0 0 24 24"
              stroke="currentColor"
            >
              <path
                strokeLinecap="round"
                strokeLinejoin="round"
                strokeWidth={2}
                d="M4 16l4.586-4.586a2 2 0 012.828 0L16 16m-2-2l1.586-1.586a2 2 0 012.828 0L20 14m-6-6h.01M6 20h12a2 2 0 002-2V6a2 2 0 00-2-2H6a2 2 0 00-2 2v12a2 2 0 002 2z"
              />
            </svg>
          </div>

          <p className="text-sm font-semibold text-zinc-200">
            Drag & drop your selfie here, or{" "}
            <span className="text-purple-400 hover:underline">browse</span>
          </p>
          <p className="mt-1.5 text-xs text-zinc-500">
            JPEG, PNG, or WEBP (Max {maxSizeMB}MB)
          </p>
        </div>
      ) : (
        <div className="relative rounded-xl border border-zinc-800 bg-zinc-900/30 p-4">
          <div className="flex items-center justify-between mb-3 border-b border-zinc-800/60 pb-3">
            <div className="flex items-center gap-2">
              <span className="text-xs font-semibold text-purple-400 uppercase tracking-wider bg-purple-950/40 px-2 py-0.5 rounded border border-purple-900/30">
                Selfie Loaded
              </span>
              <span className="text-xs text-zinc-400 truncate max-w-[150px]">
                {selectedFile?.name}
              </span>
            </div>
            <button
              onClick={() => onFileSelect(null)}
              className="text-xs font-medium text-red-400 hover:text-red-300 transition hover:underline"
            >
              Remove
            </button>
          </div>

          <div className="relative flex justify-center">
            {/* eslint-disable-next-line @next/next/no-img-element */}
            <img
              src={previewUrl}
              alt="Selfie preview"
              className="h-48 w-48 rounded-lg object-cover shadow-lg border border-zinc-800"
            />
          </div>
        </div>
      )}
    </div>
  );
}
