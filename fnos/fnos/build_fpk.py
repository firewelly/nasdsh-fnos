#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
构建 fnOS (.fpk) 安装包 —— NasDSH（Docker 后端）。

.fpk 是纯 tar.gz：
  1. 载荷（docker-image.tar.gz + ui/config + ui/images/）→ app.tgz
  2. app.tgz 的 sha256 写入 manifest 的 checksum 字段；
     同时把 manifest 的 version 同步进 cmd/service-setup 的 VERSION
  3. 包根（manifest/ICON/cmd/config/wizard/app.tgz）→ nasdsh-fnos-<ver>.fpk

前置（在 x86_64 + Docker 的机器上执行，如 fnOS 本机或 UGOS NAS）：
  docker image inspect nasdsh:<version> 必须存在
  （先 docker build -f core/Dockerfile -t nasdsh:<version> core）

用法（仓库根目录或任意位置）：
  python3 fnos/build_fpk.py [--image nasdsh:0.1.0] [--out fnos/dist/xx.fpk]
"""

import argparse
import gzip
import hashlib
import os
import re
import shutil
import subprocess
import sys
import tarfile
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.normpath(os.path.join(HERE, ".."))
FPK_ROOT = os.path.join(HERE, "fpk_root")
PAYLOAD = os.path.join(HERE, "payload")


def manifest_field(name, default=None):
    with open(os.path.join(FPK_ROOT, "manifest"), "r", encoding="utf-8") as f:
        m = re.search(r"^%s\s*=\s*(.+?)\s*$" % re.escape(name), f.read(), re.M)
    return m.group(1) if m else default


def sha256_file(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def add_file(tar, path, arcname, mode):
    info = tar.gettarinfo(path, arcname=arcname)
    info.mode = mode
    info.uid = info.gid = 0
    info.uname = info.gname = "root"
    with open(path, "rb") as f:
        tar.addfile(info, f)


def docker_save_gz(image, out_path):
    """docker save | gzip -> out_path（流式，不落 2.5GB 中间文件）"""
    save = subprocess.Popen(["docker", "save", image], stdout=subprocess.PIPE)
    with open(out_path, "wb") as raw:
        with gzip.GzipFile(fileobj=raw, mode="wb", compresslevel=6) as gz:
            while True:
                chunk = save.stdout.read(1024 * 1024)
                if not chunk:
                    break
                gz.write(chunk)
    return save.wait()


def main():
    ap = argparse.ArgumentParser()
    version = manifest_field("version", "0.1.0")
    ap.add_argument("--image", default="nasdsh:%s" % version,
                    help="本机已构建的镜像（默认 nasdsh:<manifest version>）")
    ap.add_argument("--out", default=os.path.join(HERE, "dist", "nasdsh-fnos-%s.fpk" % version))
    args = ap.parse_args()

    if not shutil.which("docker"):
        print("缺少 docker 命令（fpk 内要打包离线镜像）")
        return 1
    if subprocess.run(["docker", "image", "inspect", args.image],
                      capture_output=True).returncode != 0:
        print("本机没有镜像 %s\n先执行: docker build -f core/Dockerfile -t %s core"
              % (args.image, args.image))
        return 1

    stage = tempfile.mkdtemp(prefix="nasdsh_fpk_")
    try:
        # ---- 1. docker save | gzip ----
        image_tgz = os.path.join(stage, "docker-image.tar.gz")
        print("==> docker save %s（gzip，几分钟）" % args.image)
        if docker_save_gz(args.image, image_tgz) != 0:
            print("docker save 失败")
            return 1
        print("    镜像包 %d MB" % (os.path.getsize(image_tgz) // 1048576))

        # ---- 2. app.tgz ----
        app_tgz = os.path.join(stage, "app.tgz")
        with tarfile.open(app_tgz, "w:gz") as tar:
            add_file(tar, image_tgz, "./docker-image.tar.gz", 0o644)
            add_file(tar, os.path.join(PAYLOAD, "ui", "config"), "./ui/config", 0o644)
            for name in sorted(os.listdir(os.path.join(PAYLOAD, "ui", "images"))):
                add_file(tar, os.path.join(PAYLOAD, "ui", "images", name),
                         "./ui/images/%s" % name, 0o644)
        checksum = sha256_file(app_tgz)
        print("    app.tgz sha256=%s..." % checksum[:16])

        # ---- 3. 包根：manifest/checksum + service-setup VERSION 同步 ----
        root_stage = os.path.join(stage, "fpk")
        shutil.copytree(FPK_ROOT, root_stage)
        # 源文件可能是 000/600（OneDrive/编辑器 umask），copytree 原样保留；
        # 打包阶段统一放开属主读写，最终 tar 内的模式由 add_file 显式指定。
        for _root, _dirs, _files in os.walk(root_stage):
            for _n in _dirs + _files:
                os.chmod(os.path.join(_root, _n), 0o755 if _n in _dirs else 0o644)
        manifest_path = os.path.join(root_stage, "manifest")
        with open(manifest_path, "r", encoding="utf-8") as f:
            manifest = f.read().replace("checksum        = TO_BE_FILLED_BY_BUILD",
                                        "checksum        = %s" % checksum)
        with open(manifest_path, "w", encoding="utf-8", newline="\n") as f:
            f.write(manifest)

        svc_path = os.path.join(root_stage, "cmd", "service-setup")
        with open(svc_path, "r", encoding="utf-8") as f:
            svc = f.read()
        svc = re.sub(r'^VERSION="[^"]*"', 'VERSION="%s"' % version, svc, count=1, flags=re.M)
        with open(svc_path, "w", encoding="utf-8", newline="\n") as f:
            f.write(svc)

        for name in ("ICON.PNG", "ICON_256.PNG"):
            shutil.copy(os.path.join(ROOT, "store", "icon-256.png"),
                        os.path.join(root_stage, name))
        shutil.copy(app_tgz, os.path.join(root_stage, "app.tgz"))

        # ---- 4. .fpk ----
        os.makedirs(os.path.dirname(os.path.abspath(args.out)), exist_ok=True)
        with tarfile.open(args.out, "w:gz") as tar:
            add_file(tar, manifest_path, "./manifest", 0o644)
            for name in ("ICON.PNG", "ICON_256.PNG", "app.tgz"):
                add_file(tar, os.path.join(root_stage, name), "./%s" % name, 0o644)
            cmd_dir = os.path.join(root_stage, "cmd")
            for name in sorted(os.listdir(cmd_dir)):
                add_file(tar, os.path.join(cmd_dir, name), "./cmd/%s" % name, 0o755)
            for sub in ("config", "wizard"):
                sub_dir = os.path.join(root_stage, sub)
                for name in sorted(os.listdir(sub_dir)):
                    add_file(tar, os.path.join(sub_dir, name), "./%s/%s" % (sub, name), 0o644)

        # ---- 5. 隐私校验：产物内不得含真实凭据值（命中即失败并删除产物）----
        verifier = os.path.join(ROOT, "tools", "verify_no_keys.py")
        if os.path.isfile(verifier):
            print("==> 隐私校验 verify-no-keys")
            r = subprocess.run([sys.executable, verifier, args.out],
                               capture_output=True, text=True)
            sys.stdout.write(r.stdout or "")
            sys.stderr.write(r.stderr or "")
            if r.returncode == 2:
                os.remove(args.out)
                print("❌ 已删除产物（发现凭据，禁止分发）")
                return 1

        print("OK: %s (%.1f MB, 镜像 %s)"
              % (args.out, os.path.getsize(args.out) / 1e6, args.image))
        return 0
    finally:
        shutil.rmtree(stage, ignore_errors=True)


if __name__ == "__main__":
    sys.exit(main())
