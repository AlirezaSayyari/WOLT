# WOLT — Phase 4 operations delivery

Status: Implemented for review on the web foundation feature branch.

## Delivered scope

- Built-in device-driver registry with FortiGate SSH as the first driver.
- AES-256-GCM authenticated encryption for device credentials using an external master key.
- Device create, edit, delete, credential replacement and safe connection-test APIs.
- Pinned OpenSSH host-key validation without a shared writable known-hosts file.
- Listener create, edit and delete APIs with automatic port allocation, optimistic versions,
  allowed-source IP policy and driver-specific interface/gateway validation.
- Single-process UDP Engine Runtime that reconciles enabled database mappings.
- Pause and resume operations that close or bind UDP sockets without controlling Docker.
- Structured wake outcomes persisted to `wake_events`.
- Functional Vue pages for Devices, Listeners and Engine Control.

## Security boundary

- The API never returns passwords, decrypted credentials or ciphertext.
- The external `WOLT_MASTER_KEY` is a 32-byte random value stored only in `.env.web`.
- Every SSH connection rejects unknown or changed host keys.
- Driver errors are reduced to safe reason categories.
- Device and listener changes create immutable audit events without secret fields.

## Runtime constraints

- Web Engine Runtime is single-instance; multiple active replicas are not supported.
- The container-published UDP range remains `40000–40099`.
- A listener with retained wake events cannot be permanently deleted yet; archival UX is
  deferred to the event-retention phase.
- SQL Server compatibility remains deferred until the dedicated database phase.
