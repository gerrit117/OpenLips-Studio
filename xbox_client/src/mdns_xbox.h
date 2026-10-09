#pragma once
#include <xtl.h>
typedef int socklen_t;
struct __declspec(align(8)) sockaddr_storage {short ss_family;char padding[126];};
#define IP_MULTICAST_IF 9
#define IP_MULTICAST_TTL 10
#define IP_MULTICAST_LOOP 11
// IPv6 record storage only; the Xbox client opens IPv4 sockets exclusively.
struct in6_addr {unsigned char s6_addr[16];};
struct sockaddr_in6 {short sin6_family;unsigned short sin6_port;unsigned long sin6_flowinfo;in6_addr sin6_addr;unsigned long sin6_scope_id;};
struct ipv6_mreq {in6_addr ipv6mr_multiaddr;unsigned int ipv6mr_interface;};
static const in6_addr in6addr_any={{0}};
#ifndef AF_INET6
#define AF_INET6 23
#endif
#ifndef IPPROTO_IPV6
#define IPPROTO_IPV6 41
#endif
#define IPV6_MULTICAST_HOPS 10
#define IPV6_MULTICAST_LOOP 11
#define IPV6_JOIN_GROUP 12
#define IPV6_MULTICAST_IF 9
