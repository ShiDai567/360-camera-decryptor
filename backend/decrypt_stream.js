#!/usr/bin/env node
"use strict";

const fs = require("fs");
const path = require("path");
const vm = require("vm");
const https = require("https");
const { spawn } = require("child_process");

const DEFAULT_LIBFFMPEG_URL = "https://s4.ssl.qhres2.com/!feb3e5fa/libffmpeg.js";
const DEFAULT_CACHE_DIR = path.join(__dirname, ".cache");
const DEFAULT_LIBFFMPEG_PATH = path.join(DEFAULT_CACHE_DIR, "libffmpeg.js");

function parseArgs(argv) {
  const args = {};
  for (let i = 0; i < argv.length; i += 1) {
    const item = argv[i];
    if (!item.startsWith("--")) {
      continue;
    }
    const key = item.slice(2);
    const next = argv[i + 1];
    if (!next || next.startsWith("--")) {
      args[key] = true;
      continue;
    }
    args[key] = next;
    i += 1;
  }
  return args;
}

function log(message, quiet = false) {
  if (!quiet) {
    process.stderr.write(`${message}\n`);
  }
}

function ensureDir(dirPath) {
  fs.mkdirSync(dirPath, { recursive: true });
}

function downloadFile(url, filePath) {
  return new Promise((resolve, reject) => {
    ensureDir(path.dirname(filePath));
    const request = https.get(url, (response) => {
      if (response.statusCode >= 300 && response.statusCode < 400 && response.headers.location) {
        response.resume();
        downloadFile(response.headers.location, filePath).then(resolve, reject);
        return;
      }
      if (response.statusCode !== 200) {
        reject(new Error(`下载 libffmpeg.js 失败: HTTP ${response.statusCode}`));
        response.resume();
        return;
      }
      const file = fs.createWriteStream(filePath);
      response.pipe(file);
      file.on("finish", () => {
        file.close(resolve);
      });
      file.on("error", reject);
    });
    request.on("error", reject);
  });
}

async function ensureLibffmpeg(libffmpegPath, libffmpegUrl, quiet) {
  if (fs.existsSync(libffmpegPath)) {
    return libffmpegPath;
  }
  log(`下载 libffmpeg.js: ${libffmpegUrl}`, quiet);
  await downloadFile(libffmpegUrl, libffmpegPath);
  return libffmpegPath;
}

async function loadLibffmpeg(libffmpegPath) {
  global.self = global;
  global.performance = global.performance || { now: () => Date.now() };
  global.self.location = { href: `file://${libffmpegPath}` };
  global.document = {
    title: "",
    currentScript: { src: `file://${libffmpegPath}` },
  };

  let readyResolve;
  const ready = new Promise((resolve) => {
    readyResolve = resolve;
  });

  global.Module = {
    onRuntimeInitialized() {
      readyResolve();
    },
    onAbort(error) {
      throw new Error(String(error));
    },
  };

  const source = fs.readFileSync(libffmpegPath, "utf8");
  vm.runInThisContext(source, { filename: libffmpegPath });
  await ready;
  return global.Module;
}

function transHeapBuffer(module, ptr, length) {
  return Buffer.from(module.HEAPU8.subarray(ptr, ptr + length));
}

class FfmpegTsMuxer {
  constructor({ fps, width, height, audioChannels, audioSampleRate, audioSampleFormat, outputPath, quiet }) {
    const hasAudio = Boolean(audioChannels && audioSampleRate && audioSampleFormat);
    const audioInputArgs = hasAudio
      ? [
          "-f",
          audioSampleFormat,
          "-ar",
          String(audioSampleRate),
          "-ac",
          String(audioChannels),
          "-i",
          "pipe:3",
        ]
      : [];
    const mapArgs = hasAudio ? ["-map", "0:v:0", "-map", "1:a:0"] : ["-map", "0:v:0"];
    const audioOutputArgs = hasAudio
      ? [
          "-c:a",
          "aac",
          "-b:a",
          "48k",
          "-ac",
          String(audioChannels),
          "-ar",
          String(audioSampleRate),
        ]
      : ["-an"];
    const ffmpegArgs = [
      "-loglevel",
      "error",
      "-fflags",
      "+genpts",
      "-f",
      "rawvideo",
      "-pix_fmt",
      "yuv420p",
      "-video_size",
      `${width}x${height}`,
      "-framerate",
      String(fps),
      "-i",
      "pipe:0",
      ...audioInputArgs,
      ...mapArgs,
      "-c:v",
      "libx264",
      "-preset",
      "veryfast",
      "-tune",
      "zerolatency",
      "-g",
      String(Math.max(1, fps * 2)),
      "-keyint_min",
      String(Math.max(1, fps)),
      "-bf",
      "0",
      ...audioOutputArgs,
      "-pix_fmt",
      "yuv420p",
      "-f",
      "mpegts",
      outputPath || "pipe:1",
    ];

    this.process = spawn("ffmpeg", ffmpegArgs, {
      stdio: ["pipe", outputPath ? "ignore" : "pipe", quiet ? "ignore" : "inherit", hasAudio ? "pipe" : "ignore"],
    });
    this.videoIn = this.process.stdin;
    this.audioIn = hasAudio ? this.process.stdio[3] : null;
    this.stdout = outputPath ? null : this.process.stdout;
    this.videoPendingWrite = Promise.resolve();
    this.audioPendingWrite = Promise.resolve();
  }

  writeToStream(stream, pendingKey, frameBuffer) {
    this[pendingKey] = this[pendingKey].then(
      () =>
        new Promise((resolve, reject) => {
          if (!stream || !stream.writable) {
            resolve();
            return;
          }
          const onError = (error) => {
            stream.off("drain", onDrain);
            reject(error);
          };
          const onDrain = () => {
            stream.off("error", onError);
            resolve();
          };
          stream.once("error", onError);
          if (stream.write(frameBuffer)) {
            stream.off("error", onError);
            resolve();
            return;
          }
          stream.once("drain", onDrain);
        })
    );
    return this[pendingKey];
  }

  writeVideo(frameBuffer) {
    return this.writeToStream(this.videoIn, "videoPendingWrite", frameBuffer);
  }

  writeAudio(frameBuffer) {
    return this.writeToStream(this.audioIn, "audioPendingWrite", frameBuffer);
  }

  close() {
    if (this.videoIn && this.videoIn.writable) {
      this.videoIn.end();
    }
    if (this.audioIn && this.audioIn.writable) {
      this.audioIn.end();
    }
  }
}

class CameraWasmDecoder {
  constructor(module, options) {
    this.module = module;
    this.options = options;
    this.cacheBuffer = 0;
    this.infoPtr = 0;
    this.queue = [];
    this.inputSize = 0;
    this.opened = false;
    this.opening = false;
    this.ended = false;
    this.videoFrames = 0;
    this.audioFrames = 0;
    this.ffmpegMuxer = null;
    this.keyType = Number(options.keyType || 0);
    this.minBufferSize = Number(options.minBufferSize || 524288);
    this.decoderMemorySize = Number(options.decoderMemorySize || 5242880);
    this.chunkSize = Number(options.chunkSize || 524288);
    this.fps = Number(options.fps || 12);
    this.maxFrames = options.maxFrames ? Number(options.maxFrames) : 0;
    this.outputPath = options.outputPath || "";
    this.quiet = Boolean(options.quiet);
    this.audioSampleFormat = null;
    this.audioChannels = 0;
    this.audioSampleRate = 0;
    this.videoWidth = 0;
    this.videoHeight = 0;
  }

  async init() {
    const ret = this.module._initDecoder(this.decoderMemorySize, 0, 0, this.quiet ? 0 : 1, 0, 0);
    if (ret !== 0) {
      throw new Error(`_initDecoder 失败: ${ret}`);
    }
    this.cacheBuffer = this.module._malloc(this.chunkSize);
    this.infoPtr = this.module._malloc(28);
    this.videoCb = this.module.addFunction((ptr, size, ts, width, height) => {
      if (!this.ffmpegMuxer) {
        this.ffmpegMuxer = new FfmpegTsMuxer({
          fps: this.fps,
          width,
          height,
          audioChannels: this.audioChannels,
          audioSampleRate: this.audioSampleRate,
          audioSampleFormat: this.audioSampleFormat,
          outputPath: this.outputPath,
          quiet: this.quiet,
        });
        if (!this.outputPath && this.ffmpegMuxer.stdout) {
          this.ffmpegMuxer.stdout.pipe(process.stdout);
        }
        log(`FFmpeg muxer started: ${width}x${height} @ ${this.fps}fps`, this.quiet);
      }
      this.videoFrames += 1;
      const frame = transHeapBuffer(this.module, ptr, size);
      this.ffmpegMuxer.writeVideo(frame).catch((error) => {
        log(`写入 FFmpeg 失败: ${error.message}`, this.quiet);
        this.ended = true;
      });
      if (this.maxFrames && this.videoFrames >= this.maxFrames) {
        this.ended = true;
      }
      if (this.videoFrames <= 3) {
        log(`video frame #${this.videoFrames} ts=${ts} size=${size}`, this.quiet);
      }
    });
    this.audioCb = this.module.addFunction((ptr, size, ts, duration) => {
      this.audioFrames += 1;
      if (this.ffmpegMuxer && this.audioSampleFormat) {
        const frame = transHeapBuffer(this.module, ptr, size);
        this.ffmpegMuxer.writeAudio(frame).catch((error) => {
          log(`写入音频到 FFmpeg 失败: ${error.message}`, this.quiet);
          this.ended = true;
        });
      }
      if (this.audioFrames <= 3) {
        log(`audio frame #${this.audioFrames} ts=${ts} duration=${duration} size=${size}`, this.quiet);
      }
    });
    this.seekCb = this.module.addFunction(() => {});
  }

  enqueue(chunk) {
    if (chunk && chunk.length) {
      this.queue.push(Buffer.from(chunk));
    }
  }

  flushInput() {
    while (this.queue.length > 0) {
      const chunk = this.queue[0];
      this.module.HEAPU8.set(chunk, this.cacheBuffer);
      const wrote = this.module._sendData(this.cacheBuffer, chunk.length);
      if (wrote < 0) {
        throw new Error(`_sendData 失败: ${wrote}`);
      }
      if (wrote === 0) {
        break;
      }
      this.inputSize += wrote;
      if (wrote === chunk.length) {
        this.queue.shift();
      } else {
        this.queue[0] = chunk.subarray(wrote);
        break;
      }
    }
  }

  maybeOpen() {
    if (this.opened || this.opening || this.inputSize < this.minBufferSize) {
      return;
    }
    this.opening = true;
    const keyPtr = this.options.playKey ? this.module.allocateUTF8(this.options.playKey) : 0;
    const relayPtr = this.options.relaySig ? this.module.allocateUTF8(this.options.relaySig) : 0;
    const ret = this.module._openDecoder(
      this.infoPtr,
      7,
      this.videoCb,
      this.audioCb,
      this.seekCb,
      keyPtr,
      this.keyType,
      relayPtr,
      0
    );
    this.opening = false;
    if (ret !== 0) {
      throw new Error(`_openDecoder 失败: ${ret}`);
    }
    this.opened = true;
    const info = Array.from(this.module.HEAP32.subarray(this.infoPtr >> 2, (this.infoPtr >> 2) + 7));
    this.videoWidth = info[2];
    this.videoHeight = info[3];
    this.audioSampleFormat = this.mapAudioSampleFormat(info[4]);
    this.audioChannels = info[5];
    this.audioSampleRate = info[6];
    log(`Decoder opened: duration=${info[0]}s width=${info[2]} height=${info[3]}`, this.quiet);
  }

  mapAudioSampleFormat(sampleFmt) {
    const formatMap = {
      0: "u8",
      1: "s16le",
      2: "s32le",
      3: "f32le",
      5: "u8",
      6: "s16le",
      7: "s32le",
      8: "f32le",
      9: "f64le",
      10: "s64le",
      11: "s64le",
    };
    return formatMap[sampleFmt] || null;
  }

  pumpDecode(maxIterations = 256) {
    if (!this.opened || this.ended) {
      return;
    }
    for (let i = 0; i < maxIterations; i += 1) {
      const ret = this.module._decodeOnePacket();
      if (ret === 0) {
        continue;
      }
      if (ret === 9) {
        return;
      }
      if (ret === 7) {
        this.ended = true;
        return;
      }
      throw new Error(`_decodeOnePacket 失败: ${ret}`);
    }
  }

  finish() {
    this.ended = true;
    if (this.ffmpegMuxer) {
      this.ffmpegMuxer.close();
    }
  }
}

async function* chunkFromFile(filePath, chunkSize) {
  const handle = await fs.promises.open(filePath, "r");
  try {
    let position = 0;
    while (true) {
      const buffer = Buffer.alloc(chunkSize);
      const { bytesRead } = await handle.read(buffer, 0, chunkSize, position);
      if (!bytesRead) {
        break;
      }
      position += bytesRead;
      yield buffer.subarray(0, bytesRead);
    }
  } finally {
    await handle.close();
  }
}

async function* chunkFromFetch(url, chunkSize, quiet) {
  log(`fetch stream: ${url}`, quiet);
  const response = await fetch(url, {
    headers: {
      Referer: "https://my.jia.360.cn/",
      "User-Agent": "Mozilla/5.0",
      Accept: "*/*",
    },
  });
  if (!response.ok || !response.body) {
    throw new Error(`拉取视频流失败: HTTP ${response.status}`);
  }
  let pending = Buffer.alloc(0);
  for await (const rawChunk of response.body) {
    pending = Buffer.concat([pending, Buffer.from(rawChunk)]);
    while (pending.length >= chunkSize) {
      yield pending.subarray(0, chunkSize);
      pending = pending.subarray(chunkSize);
    }
  }
  if (pending.length > 0) {
    yield pending;
  }
}

async function main() {
  const args = parseArgs(process.argv.slice(2));
  if (!args.url && !args["input-file"]) {
    throw new Error("需要传入 --url 或 --input-file");
  }
  if (!args["play-key"]) {
    throw new Error("需要传入 --play-key");
  }

  const quiet = Boolean(args.quiet);
  const libffmpegUrl = args["libffmpeg-url"] || process.env.CAMERA_LIBFFMPEG_URL || DEFAULT_LIBFFMPEG_URL;
  const libffmpegPath = path.resolve(args["libffmpeg-path"] || DEFAULT_LIBFFMPEG_PATH);
  const chunkSize = Number(args["network-chunk-size"] || 64 * 1024);

  await ensureLibffmpeg(libffmpegPath, libffmpegUrl, quiet);
  const module = await loadLibffmpeg(libffmpegPath);
  const decoder = new CameraWasmDecoder(module, {
    playKey: args["play-key"],
    relaySig: args["relay-sig"] || "",
    keyType: args["key-type"] || 0,
    fps: args.fps || 12,
    outputPath: args.output || "",
    maxFrames: args["max-frames"] || 0,
    quiet,
  });
  await decoder.init();

  const source = args["input-file"]
    ? chunkFromFile(path.resolve(args["input-file"]), chunkSize)
    : chunkFromFetch(args.url, chunkSize, quiet);

  for await (const chunk of source) {
    decoder.enqueue(chunk);
    decoder.flushInput();
    decoder.maybeOpen();
    decoder.pumpDecode();
    if (decoder.ended) {
      break;
    }
  }

  decoder.finish();
  log(`decoder finished: videoFrames=${decoder.videoFrames} audioFrames=${decoder.audioFrames}`, quiet);
}

main().catch((error) => {
  process.stderr.write(`${error.stack || error.message}\n`);
  process.exit(1);
});
