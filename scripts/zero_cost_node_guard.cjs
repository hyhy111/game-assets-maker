'use strict';

const dns = require('node:dns');
const dnsPromises = require('node:dns/promises');
const net = require('node:net');

const BLOCKED_MESSAGE = 'external network is disabled by the zero-cost test runner';
const DNS_METHODS = [
  'lookup', 'resolve', 'resolve4', 'resolve6', 'resolveAny', 'resolveCaa',
  'resolveCname', 'resolveMx', 'resolveNaptr', 'resolveNs', 'resolvePtr',
  'resolveSoa', 'resolveSrv', 'resolveTxt', 'reverse',
];

function isLoopback(host) {
  if (host === undefined || host === null || host === '') return true;
  const value = String(host).toLowerCase().replace(/^\[|\]$/g, '');
  return value === 'localhost'
    || value === '::1'
    || value.startsWith('127.')
    || value.startsWith('::ffff:127.');
}

function requireLoopback(host) {
  if (!isLoopback(host)) throw new Error(BLOCKED_MESSAGE);
}

function connectHost(args) {
  const first = args[0];
  if (typeof first === 'object' && first !== null) {
    if (first.path) return null;
    return first.host ?? first.hostname ?? 'localhost';
  }
  if (typeof first === 'number') {
    return typeof args[1] === 'string' ? args[1] : 'localhost';
  }
  return null;
}

const originalConnect = net.Socket.prototype.connect;
net.Socket.prototype.connect = function zeroCostConnect(...args) {
  const host = connectHost(args);
  if (host !== null) requireLoopback(host);
  return originalConnect.apply(this, args);
};

const originalCreateConnection = net.createConnection;
net.createConnection = function zeroCostCreateConnection(...args) {
  const host = connectHost(args);
  if (host !== null) requireLoopback(host);
  return originalCreateConnection.apply(this, args);
};
net.connect = net.createConnection;

for (const name of DNS_METHODS) {
  const original = dns[name];
  if (typeof original !== 'function') continue;
  dns[name] = function zeroCostDns(host, ...args) {
    requireLoopback(host);
    return original.call(this, host, ...args);
  };
}

for (const name of DNS_METHODS) {
  const original = dnsPromises[name];
  if (typeof original !== 'function') continue;
  dnsPromises[name] = function zeroCostDnsPromise(host, ...args) {
    requireLoopback(host);
    return original.call(this, host, ...args);
  };
}
