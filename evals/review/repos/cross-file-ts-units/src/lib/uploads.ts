import { UPLOAD_LIMIT_MB } from "@/lib/config";

export const tooBig = (bytes: number) => bytes > UPLOAD_LIMIT_MB * 1024 * 1024;
