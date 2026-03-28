# Multi-stage build: PostgreSQL 17 with RDKit cartridge, pgvector, Apache AGE, TimescaleDB
# Build time: ~30-60 minutes (RDKit is the bottleneck)
# Uses trixie (Debian 13) for Boost 1.83 — required by RDKit 2026.03

# ==============================================================================
# Stage 1: Build all extensions from source
# ==============================================================================
FROM postgres:17-trixie AS builder

ENV DEBIAN_FRONTEND=noninteractive

RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    postgresql-server-dev-17 \
    cmake \
    libboost-all-dev \
    libeigen3-dev \
    git \
    curl \
    ca-certificates \
    flex \
    bison \
    libssl-dev \
    pkg-config \
    && rm -rf /var/lib/apt/lists/*

# --- pgvector v0.8.2 (fastest build, ~30s) ---
RUN cd /tmp \
    && git clone --branch v0.8.2 --depth 1 https://github.com/pgvector/pgvector.git \
    && cd pgvector \
    && make -j$(nproc) \
    && make install

# --- Apache AGE v1.7.0 (PG17 branch, ~2-3min) ---
RUN cd /tmp \
    && git clone --branch release/PG17/1.7.0 --depth 1 https://github.com/apache/age.git \
    && cd age \
    && make -j$(nproc) \
    && make install

# --- TimescaleDB 2.26.0 (~3-5min) ---
RUN cd /tmp \
    && git clone --branch 2.26.0 --depth 1 https://github.com/timescale/timescaledb.git \
    && cd timescaledb \
    && ./bootstrap -DREGRESS_CHECKS=OFF -DWARNINGS_AS_ERRORS=OFF \
    && cd build \
    && make -j$(nproc) \
    && make install

# --- RDKit Cartridge Release_2026_03_1 (longest build, ~20-40min) ---
RUN cd /tmp \
    && git clone --branch Release_2026_03_1 --depth 1 https://github.com/rdkit/rdkit.git \
    && cd rdkit \
    && mkdir build && cd build \
    && cmake .. \
        -DRDK_BUILD_PGSQL=ON \
        -DRDK_BUILD_PYTHON_WRAPPERS=OFF \
        -DRDK_BUILD_CPP_TESTS=OFF \
        -DRDK_BUILD_DESCRIPTORS3D=OFF \
        -DRDK_BUILD_COORDGEN_SUPPORT=OFF \
        -DRDK_BUILD_MAEPARSER_SUPPORT=OFF \
        -DRDK_BUILD_INCHI_SUPPORT=ON \
        -DRDK_BUILD_FREETYPE_SUPPORT=OFF \
        -DRDK_BUILD_CAIRO_SUPPORT=OFF \
        -DRDK_BUILD_CHEMDRAW_SUPPORT=OFF \
        -DRDK_BUILD_SWIG_WRAPPERS=OFF \
        -DRDK_BUILD_CFFI_LIB=OFF \
        -DRDK_BUILD_YAEHMOP_SUPPORT=OFF \
        -DRDK_BUILD_XYZ2MOL_SUPPORT=OFF \
        -DRDK_USE_URF=OFF \
        -DRDK_BUILD_THREADSAFE_SSS=ON \
        -DPostgreSQL_CONFIG=/usr/bin/pg_config \
        -DPostgreSQL_INCLUDE_DIR=/usr/include/postgresql/17/server \
        -DCMAKE_BUILD_TYPE=Release \
    && make -j$(nproc) \
    && make install

# ==============================================================================
# Stage 2: Runtime image with only compiled artifacts
# ==============================================================================
FROM postgres:17-trixie

ENV DEBIAN_FRONTEND=noninteractive

# Runtime dependencies for RDKit shared libraries
RUN apt-get update && apt-get install -y --no-install-recommends \
    libboost-serialization1.83.0 \
    libboost-regex1.83.0 \
    libboost-system1.83.0 \
    libboost-iostreams1.83.0 \
    && rm -rf /var/lib/apt/lists/*

# Copy extension shared objects (.so)
COPY --from=builder /usr/lib/postgresql/17/lib/ /usr/lib/postgresql/17/lib/

# Copy extension SQL and control files
COPY --from=builder /usr/share/postgresql/17/extension/ /usr/share/postgresql/17/extension/

# Copy RDKit shared libraries that the cartridge .so links against
COPY --from=builder /usr/local/lib/libRDKit*.so* /usr/local/lib/
COPY --from=builder /usr/local/lib/libFreeSASA*.so* /usr/local/lib/
RUN ldconfig

# Preload TimescaleDB and AGE (pgvector and rdkit load on CREATE EXTENSION)
RUN echo "shared_preload_libraries = 'timescaledb,age'" >> /usr/share/postgresql/postgresql.conf.sample

# Init script: create extensions, graph, and schemas
COPY init.sql /docker-entrypoint-initdb.d/001-init.sql
