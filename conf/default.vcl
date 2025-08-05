vcl 4.1;
import uri;
import std;
import utils;
import goto;
import accounting;
import stat;

backend default none;

sub vcl_init {
	accounting.create_namespace("lucid");
}

sub vcl_recv {
	set req.url = uri.decode(req.url);
	accounting.set_namespace("lucid");

	if (req.method != "GET" &&
		req.method != "HEAD" &&
		req.method != "PUT" &&
		req.method != "POST" &&
		req.method != "TRACE" &&
		req.method != "OPTIONS" &&
		req.method != "DELETE" &&
		req.method != "PATCH") {
		return (synth(405));
	}

	if (req.url == "/metrics") {
		return(pass);
	}

	unset req.http.x-method;
	set req.http.x-method = req.method;

	accounting.add_keys(req.method);

	# Only cache GET requests
	if (req.method != "GET") {
		return (pass);
	}

	# Save the range and reuse it on the backend
	# request. This because AWSv4 includes the
	# range header in the signature, which means
	# that it cannot be changed without re-signing
	# the request.
	unset req.http.x-range;
	if (req.http.Range) {
		set req.http.x-range = req.http.Range;
		unset req.http.Range;
	}
	return (hash);
}

sub vcl_hash {
	hash_data(req.method);

	# It would be better to use vmod-slicer to normalize byte ranges, but we
	# cannot do that currently because the range header is part of the AWSv4
	# signature and cannot be changed.
	hash_data(req.http.x-range);
}

sub vcl_backend_fetch {
	if (bereq.url == "/metrics") {
		set bereq.backend = stat.backend_prometheus();
		return(fetch);
	}

	if (bereq.http.x-method) {
		set bereq.method = bereq.http.x-method;
		unset bereq.http.x-method;
	}

	if (bereq.http.x-range) {
		set bereq.http.range = bereq.http.x-range;
		unset bereq.http.x-range;
	}

	# Create a TLS backend using the incoming host header.
	set bereq.backend = goto.dns_backend(bereq.http.host, ssl=true);
}

sub vcl_backend_response {
	if (beresp.status == 200 || beresp.status == 206 || beresp.status == 304) {
		unset beresp.http.cache-control;
		unset beresp.http.expires;
		set beresp.ttl = 10y;
	}
}
