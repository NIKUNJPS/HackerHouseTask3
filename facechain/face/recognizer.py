"""Real face detection + 128-D face embeddings using OpenCV's YuNet + SFace.

* YuNet  (face_detection_yunet)   — detects faces and 5 landmarks.
* SFace  (face_recognition_sface) — aligns the crop and produces a 128-D
  embedding whose cosine similarity separates identities
  (same person > ~0.363 > different person).

No dlib / no heavyweight deep-learning framework required — OpenCV's DNN module
runs the ONNX models directly.
"""
from __future__ import annotations

import base64
import hashlib
from dataclasses import dataclass, field
from pathlib import Path

import cv2
import numpy as np

from .. import config
from . import models

# OpenCV 4.13's new DNN graph engine prints harmless "Targets are not supported"
# warnings when the models load. Quiet them so the pipeline output stays clean.
try:
    cv2.utils.logging.setLogLevel(cv2.utils.logging.LOG_LEVEL_ERROR)
except Exception:
    pass


class NoFaceFound(Exception):
    """Raised when no face can be detected in an image."""


@dataclass
class DetectedFace:
    box: tuple[int, int, int, int]          # x, y, w, h
    score: float                            # detector confidence
    embedding: np.ndarray = field(repr=False)  # 128-D float32, L2-normalised

    @property
    def embedding_bytes(self) -> bytes:
        # canonical little-endian float32 bytes (stable across runs/platforms)
        return np.ascontiguousarray(self.embedding, dtype="<f4").tobytes()

    @property
    def embedding_sha256(self) -> str:
        return hashlib.sha256(self.embedding_bytes).hexdigest()

    @property
    def embedding_b64(self) -> str:
        return base64.b64encode(self.embedding_bytes).decode("ascii")


def cosine(a: np.ndarray, b: np.ndarray) -> float:
    a = a.astype(np.float64).flatten()
    b = b.astype(np.float64).flatten()
    denom = np.linalg.norm(a) * np.linalg.norm(b)
    if denom == 0:
        return 0.0
    return float(np.dot(a, b) / denom)


class FaceRecognizer:
    """Loads the models once and exposes detect/encode/compare helpers."""

    def __init__(self) -> None:
        det_path, rec_path = models.ensure_models()
        self._detector = cv2.FaceDetectorYN.create(
            str(det_path), "", (320, 320), config.FACE_DETECT_SCORE, 0.3, 5000
        )
        self._recognizer = cv2.FaceRecognizerSF.create(str(rec_path), "")

    # -- low level -----------------------------------------------------------
    @staticmethod
    def _read(image_path: str | Path) -> np.ndarray:
        img = cv2.imread(str(image_path))
        if img is None:
            raise FileNotFoundError(f"could not read image: {image_path}")
        return img

    def _detect(self, img: np.ndarray) -> np.ndarray:
        h, w = img.shape[:2]
        self._detector.setInputSize((w, h))
        _, faces = self._detector.detect(img)
        if faces is None:
            return np.empty((0, 15), dtype=np.float32)
        # sort by area, largest first
        return np.array(sorted(faces, key=lambda f: f[2] * f[3], reverse=True))

    def _encode(self, img: np.ndarray, face_row: np.ndarray) -> np.ndarray:
        aligned = self._recognizer.alignCrop(img, face_row)
        feat = self._recognizer.feature(aligned)
        vec = feat.flatten().astype(np.float32)
        norm = np.linalg.norm(vec)
        return vec / norm if norm else vec

    # -- public --------------------------------------------------------------
    def detect_faces(self, image_path: str | Path) -> list[DetectedFace]:
        """Detect and encode every face in an image (largest first)."""
        img = self._read(image_path)
        faces = self._detect(img)
        out: list[DetectedFace] = []
        for row in faces:
            x, y, w, h = (int(v) for v in row[:4])
            out.append(
                DetectedFace(
                    box=(x, y, w, h),
                    score=float(row[-1]),
                    embedding=self._encode(img, row),
                )
            )
        return out

    def primary_face(self, image_path: str | Path) -> DetectedFace:
        """Return the most prominent (largest) face or raise NoFaceFound."""
        faces = self.detect_faces(image_path)
        if not faces:
            raise NoFaceFound(f"no face detected in {image_path}")
        return faces[0]

    def compare(self, a: np.ndarray, b: np.ndarray) -> tuple[float, bool]:
        """Return (cosine_similarity, is_same_identity)."""
        sim = cosine(a, b)
        return sim, sim >= config.FACE_COSINE_THRESHOLD

    # -- visualisation (nice for the demo recording) -------------------------
    def annotate(self, image_path: str | Path, out_path: str | Path,
                 label: str = "FACE") -> Path:
        """Draw the detected face box + score and save to out_path."""
        img = self._read(image_path)
        for row in self._detect(img):
            x, y, w, h = (int(v) for v in row[:4])
            cv2.rectangle(img, (x, y), (x + w, y + h), (0, 220, 0), 2)
            cv2.putText(img, f"{label} {row[-1]:.2f}", (x, max(0, y - 8)),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 220, 0), 2)
        out_path = Path(out_path)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        cv2.imwrite(str(out_path), img)
        return out_path
