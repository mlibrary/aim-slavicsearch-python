FROM debian:bullseye

LABEL maintainer="dfulmer@umich.edu"

RUN apt-get update && apt-get install -y git

RUN apt-get update -yqq && apt-get install -yqq wget curl --no-install-recommends \
  build-essential\
  perl\
  cpanminus\
  libxml2-dev\
  libxslt1-dev\
  libyaz-dev\
  yaz\
  python3\
  python3-pip

RUN wget --no-check-certificate http://ftp.indexdata.dk/pub/yaz/yaz-5.30.0.tar.gz
RUN tar -xzf yaz-5.30.0.tar.gz
RUN cd yaz-5.30.0 && ./configure && make && make install

RUN cpanm MARC::Batch
RUN cpanm MARC::Lint
RUN cpanm Net::Z3950::ZOOM
RUN cpanm Dotenv

RUN pip3 install --no-cache-dir requests
RUN pip3 install --no-cache-dir pymarc
RUN pip3 install --no-cache-dir pytest
RUN pip3 install --no-cache-dir bookops-worldcat

ARG UNAME=app
ARG UID=1000
ARG GID=1000
RUN groupadd -g ${GID} -o ${UNAME}
RUN useradd -m -d /app -u ${UID} -g ${GID} -o -s /bin/bash ${UNAME}
USER $UNAME

WORKDIR /app
ENV PERL5LIB=/app/lib