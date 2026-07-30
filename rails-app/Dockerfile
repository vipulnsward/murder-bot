ARG RUBY_VERSION=3.3.12
FROM ruby:${RUBY_VERSION}-slim AS base

WORKDIR /rails
ENV RAILS_ENV=production BUNDLE_DEPLOYMENT=1 BUNDLE_PATH=/usr/local/bundle BUNDLE_WITHOUT=development:test

RUN apt-get update -qq && \
    apt-get install --no-install-recommends -y curl libpq5 postgresql-client && \
    rm -rf /var/lib/apt/lists/*

FROM base AS build

RUN apt-get update -qq && \
    apt-get install --no-install-recommends -y build-essential libpq-dev && \
    rm -rf /var/lib/apt/lists/*

COPY Gemfile Gemfile.lock ./
RUN bundle install && rm -rf /usr/local/bundle/ruby/*/cache

COPY . .
RUN bundle exec bootsnap precompile app/ lib/

FROM base

COPY --from=build /usr/local/bundle /usr/local/bundle
COPY --from=build /rails /rails
RUN useradd --create-home --uid 1000 rails && chown -R rails:rails db log storage tmp
USER rails

ENTRYPOINT ["/rails/bin/docker-entrypoint"]
EXPOSE 3000
CMD ["./bin/rails", "server", "-b", "0.0.0.0"]
