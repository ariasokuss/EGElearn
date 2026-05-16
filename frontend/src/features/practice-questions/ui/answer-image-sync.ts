export type AnswerImageLike = Pick<File, "name" | "size" | "lastModified">;

export type UploadedAnswerImageKeyMap = Record<string, string>;

export function fileFingerprint(file: AnswerImageLike): string {
  return `${file.name}:${file.size}:${file.lastModified}`;
}

export async function syncAnswerImageKeys<TFile extends AnswerImageLike>({
  files,
  uploadedByFingerprint,
  uploadFile,
}: {
  files: TFile[];
  uploadedByFingerprint: UploadedAnswerImageKeyMap;
  uploadFile: (file: TFile) => Promise<string | null>;
}): Promise<string[]> {
  const imageKeys: string[] = [];

  for (const file of files) {
    const fingerprint = fileFingerprint(file);
    let imageKey: string | null = uploadedByFingerprint[fingerprint] ?? null;
    if (!imageKey) {
      imageKey = await uploadFile(file);
      if (imageKey) uploadedByFingerprint[fingerprint] = imageKey;
    }
    if (imageKey) imageKeys.push(imageKey);
  }

  return imageKeys;
}

export function removeUploadedAnswerImageKey(
  uploadedByFingerprint: UploadedAnswerImageKeyMap,
  file: AnswerImageLike,
): void {
  delete uploadedByFingerprint[fileFingerprint(file)];
}
