import { useState } from "react";
import {
  AppWindow,
  Boxes,
  Laptop,
  Pencil,
  Plus,
  Search,
  Server,
} from "lucide-react";
import {
  Badge,
  Empty,
  ErrorBox,
  Loading,
  Modal,
  PageHeader,
  humanize,
  useToast,
} from "../components/ui";
import { useResource } from "../hooks/useResource";
import { useAuth } from "../store/AuthContext";
import { api, errorMessage, reconcile } from "../services/api";
import type { Asset } from "../types";

function AssetEditor({
  asset,
  close,
}: {
  asset: Asset | null;
  close: () => void;
}) {
  const [values, setValues] = useState({
    hostname: asset?.hostname ?? "",
    ip_address: asset?.ip_address ?? "",
    type: asset?.type ?? "server",
    environment: asset?.environment ?? "lab",
    owner: asset?.owner ?? "Security operations",
    status: asset?.status ?? "active",
  });
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const notify = useToast();
  async function submit(event: React.FormEvent) {
    event.preventDefault();
    setBusy(true);
    setError(null);
    try {
      if (asset) await api.patch(`/assets/${asset.id}`, values);
      else await api.post("/assets", values);
      reconcile();
      notify("Device details saved. This does not connect it for monitoring.");
      close();
    } catch (err) {
      setError(errorMessage(err));
    } finally {
      setBusy(false);
    }
  }
  return (
    <form className="stack-form" onSubmit={submit}>
      {["hostname", "ip_address", "environment", "owner"].map((key) => (
        <label key={key}>
          {key === "ip_address" ? "IP address" : humanize(key)}
          <input
            value={values[key as keyof typeof values]}
            maxLength={key === "environment" ? 30 : key === "owner" ? 100 : 253}
            onChange={(event) =>
              setValues({ ...values, [key]: event.target.value })
            }
            required
          />
        </label>
      ))}
      <div className="form-row">
        <label>
          Type
          <select
            value={values.type}
            onChange={(event) =>
              setValues({ ...values, type: event.target.value })
            }
          >
            {["server", "application", "endpoint"].map((item) => (
              <option key={item} value={item}>
                {humanize(item)}
              </option>
            ))}
          </select>
        </label>
        <label>
          Status
          <select
            value={values.status}
            onChange={(event) =>
              setValues({ ...values, status: event.target.value })
            }
          >
            <option value="active">Active</option>
            <option value="inactive">Inactive</option>
          </select>
        </label>
      </div>
      <ErrorBox message={error} />
      <div className="form-actions">
        <button type="button" className="button secondary" onClick={close}>
          Cancel
        </button>
        <button className="button primary" disabled={busy}>
          Save device details
        </button>
      </div>
    </form>
  );
}
export function AssetsPage() {
  const { data, error, loading, reload } = useResource<{ items: Asset[] }>(
    "/assets",
  );
  const { user } = useAuth();
  const [query, setQuery] = useState("");
  const [editing, setEditing] = useState<Asset | null | undefined>(undefined);
  const assets =
    data?.items.filter((asset) =>
      `${asset.hostname} ${asset.ip_address} ${asset.owner}`
        .toLowerCase()
        .includes(query.toLowerCase()),
    ) ?? [];
  return (
    <>
      <PageHeader
        title="Device list"
        description="Keep device details for investigations. Adding a device here does not connect it for monitoring."
        actions={
          user?.role === "ADMIN" && (
            <button className="button primary" onClick={() => setEditing(null)}>
              <Plus size={17} />
              Add device details
            </button>
          )
        }
      />
      <div className="panel">
        <div className="filter-bar">
          <div className="search-field">
            <Search size={17} />
            <input
              aria-label="Search devices"
              placeholder="Search computer name, address, or owner…"
              value={query}
              onChange={(event) => setQuery(event.target.value)}
            />
          </div>
          <span className="count-chip">
            <Boxes size={16} />
            {assets.length} devices
          </span>
        </div>
        <ErrorBox message={error} retry={reload} />
        {loading && !data ? (
          <Loading />
        ) : assets.length ? (
          <div className="table-scroll">
            <table>
              <thead>
                <tr>
                  <th>Device</th>
                  <th>IP address</th>
                  <th>Type</th>
                  <th>Environment</th>
                  <th>Owner</th>
                  <th>Status</th>
                  {user?.role === "ADMIN" && <th />}
                </tr>
              </thead>
              <tbody>
                {assets.map((asset) => (
                  <tr key={asset.id}>
                    <td>
                      <div className="asset-name">
                        <span className="asset-icon">
                          {asset.type === "server" ? (
                            <Server size={19} />
                          ) : asset.type === "endpoint" ? (
                            <Laptop size={19} />
                          ) : (
                            <AppWindow size={19} />
                          )}
                        </span>
                        <strong>{asset.hostname}</strong>
                      </div>
                    </td>
                    <td>
                      <code>{asset.ip_address}</code>
                    </td>
                    <td>{humanize(asset.type)}</td>
                    <td>
                      <span className="source-tag">{asset.environment}</span>
                    </td>
                    <td>{asset.owner}</td>
                    <td>
                      <Badge value={asset.status} />
                    </td>
                    {user?.role === "ADMIN" && (
                      <td>
                        <button
                          className="icon-button"
                          aria-label={`Edit ${asset.hostname}`}
                          onClick={() => setEditing(asset)}
                        >
                          <Pencil size={16} />
                        </button>
                      </td>
                    )}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ) : (
          <Empty
            title="No devices found"
            description="Try another search or add device details. Use Connected systems to set up monitoring."
          />
        )}
      </div>
      <div className="notice inventory-notice">
        <Server size={17} />
        <p>
          An administrator sets this device status. “Active” does not prove that a helper is connected or a device is healthy. Check Connected systems for collection status.
        </p>
      </div>
      {editing !== undefined && (
        <Modal
          title={editing ? "Edit device details" : "Add device details"}
          onClose={() => setEditing(undefined)}
        >
          <AssetEditor asset={editing} close={() => setEditing(undefined)} />
        </Modal>
      )}
    </>
  );
}
