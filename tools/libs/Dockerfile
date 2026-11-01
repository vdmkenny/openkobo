# Cross-build the media/parsing libraries for Kobo (armv7 hard-float, old glibc).
#
# Stage 1 builds the koreader "koxtoolchain" for arm-kobo-linux-gnueabihf, whose
# glibc is old enough for every supported Kobo (verified per-library in stage 2,
# which fails the build if any library needs a newer glibc than the device has).
# Stage 2 cross-builds the libraries into /home/builder/out.

# ---- stage 1: toolchain -----------------------------------------------------
FROM ubuntu:22.04 AS toolchain
ENV DEBIAN_FRONTEND=noninteractive
RUN apt-get update && apt-get install -y --no-install-recommends \
        autoconf automake bison flex gawk gettext git gperf help2man \
        libncurses-dev libtool-bin make patch pkg-config python3 texinfo \
        unzip wget xz-utils bzip2 g++ gcc file rsync ca-certificates \
    && rm -rf /var/lib/apt/lists/*
# crosstool-NG (which koxtoolchain drives) refuses to run as root.
RUN useradd -m builder
USER builder
WORKDIR /home/builder
RUN git clone --depth 1 https://github.com/koreader/koxtoolchain
RUN cd koxtoolchain && ./gen-tc.sh kobo
# toolchain now at /home/builder/x-tools/arm-kobo-linux-gnueabihf

# ---- stage 2: libraries -----------------------------------------------------
FROM toolchain AS libs
# cmake here (not in stage 1) so the cached toolchain layer is not invalidated.
USER root
RUN apt-get update && apt-get install -y --no-install-recommends cmake \
    && rm -rf /var/lib/apt/lists/*
USER builder
ENV TC=/home/builder/x-tools/arm-kobo-linux-gnueabihf
ENV PATH=$TC/bin:$PATH
COPY --chown=builder:builder build-libs.sh /home/builder/build-libs.sh
RUN sh /home/builder/build-libs.sh
