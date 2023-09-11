import time
from typing import Optional

from docker import DockerClient, errors, from_env
from halo import Halo
from typer import Argument, Option, Typer, colors, secho

DEFAULT_NETWORK_NAME = "cont_net"

cli = Typer()


def wait_healtcheck(docker: DockerClient, container_id: str) -> None:
    with Halo("waiting for the condition", text_color="green"):
        ready = False
        while not ready:
            container = docker.containers.get(container_id)
            health_status = container.attrs["State"]["Health"]["Status"]
            ready = health_status == "healthy"
            time.sleep(0.1)
    secho("Container is ", nl=False)
    secho("healthy", fg=colors.BRIGHT_GREEN, nl=False)
    secho("!")


def declare_network(docker: DockerClient, network: str) -> None:
    with Halo(f"Creating network {network}", text_color="green"):
        try:
            docker.networks.get(network)
        except errors.NotFound:
            docker.networks.create(
                network,
                attachable=True,
            )


def pull_img(docker: DockerClient, repo: str, tag: str) -> str:
    with Halo(f"Pulling image {repo}:{tag}", text_color="green"):
        img = docker.images.pull(repo, tag=tag)
    return img.attrs["RepoTags"][0]


def print_network_settings(docker: DockerClient, container_id: str) -> None:
    secho("Container IPs:")
    container = docker.containers.get(container_id)
    networks = container.attrs["NetworkSettings"]["Networks"]
    for network, nconfig in networks.items():
        secho(f"\t{network}: ", nl=False)
        secho(nconfig["IPAddress"], fg=colors.GREEN)


@cli.command(help="Run postgres container")
def pg(
    name: Optional[str] = Argument(None, help="Container name"),
    db_name: str = Option(
        "postgres",
        help="Name of the database. User and password match this value",
    ),
    network: str = Option(
        DEFAULT_NETWORK_NAME,
        help="Network name to attach container to",
    ),
    port: int = Option(5432, help="Host port to expose"),
    tag: str = Option("15.4-bullseye", help="Image tag to use"),
) -> None:
    docker = from_env()
    img = pull_img(docker, "postgres", tag)
    declare_network(docker, network)
    volumes = None
    if name is not None:
        volumes = {f"{name}-pg-db": {"bind": "/var/lib/postgresql/data", "mode": "rw"}}
    container = docker.containers.run(
        name=name,
        image=img,
        remove=True,
        detach=True,
        network=network,
        hostname=name or "pg",
        healthcheck={
            "test": f"pg_isready -U {db_name}",
            "interval": 2 * 1000 * 1000000,
            "timeout": 3 * 1000 * 1000000,
            "retries": 40,
        },
        ports={
            "5432": port,
        },
        volumes=volumes,
        environment={
            "POSTGRES_PASSWORD": db_name,
            "POSTGRES_USER": db_name,
            "POSTGRES_DB": db_name,
        },
    )
    secho("Container ", nl=False)
    secho(container.short_id, nl=False, fg=colors.GREEN)
    secho(" successfully started")
    wait_healtcheck(docker, container.id)
    print_network_settings(docker, container.id)


@cli.command(help="Run timescaledb container")
def timescale(
    name: Optional[str] = Argument(None, help="Container name"),
    db_name: str = Option(
        "timescale",
        help="Name of the database. User and password match this value",
    ),
    port: int = Option(5432, help="Host port to expose"),
    network: str = Option(
        DEFAULT_NETWORK_NAME,
        help="Network name to attach container to",
    ),
    tag: str = Option("2.11.2-pg15", help="Image tag to use"),
) -> None:
    docker = from_env()
    img = pull_img(docker, "timescale/timescaledb", tag)
    declare_network(docker, network)
    volumes = None
    if name is not None:
        volumes = {f"{name}-ts-db": {"bind": "/var/lib/postgresql/data", "mode": "rw"}}
    container = docker.containers.run(
        name=name,
        image=img,
        remove=True,
        detach=True,
        network=network,
        hostname=name or "timescale",
        healthcheck={
            "test": f"pg_isready -U {db_name}",
            "interval": 2 * 1000 * 1000000,
            "timeout": 3 * 1000 * 1000000,
            "retries": 40,
        },
        ports={
            "5432": port,
        },
        volumes=volumes,
        environment={
            "POSTGRES_PASSWORD": db_name,
            "POSTGRES_USER": db_name,
            "POSTGRES_DB": db_name,
        },
    )
    secho("Container ", nl=False)
    secho(container.short_id, nl=False, fg=colors.GREEN)
    secho(" successfully started")
    wait_healtcheck(docker, container.id)
    print_network_settings(docker, container.id)


@cli.command(help="Run rabbitMQ container")
def rmq(
    name: Optional[str] = Argument(None, help="Container name"),
    port: int = Option(5672, help="Port to open for AMQP protocol"),
    ui_port: int = Option(15672, help="Port to open for management UI"),
    username: str = Option("guest", help="Admin username"),
    password: str = Option("guest", help="Admin password"),
    network: str = Option(
        DEFAULT_NETWORK_NAME,
        help="Network name to attach container to",
    ),
    tag: str = Option("3.10.23-management", help="Image tag to use"),
):
    docker = from_env()
    img = pull_img(docker, "rabbitmq", tag)
    declare_network(docker, network)
    container = docker.containers.run(
        name=name,
        image=img,
        remove=True,
        detach=True,
        network=network,
        hostname=name or "rmq",
        healthcheck={
            "test": "rabbitmq-diagnostics check_running -q",
            "interval": 3 * 1000 * 1000000,
            "timeout": 3 * 1000 * 1000000,
            "retries": 50,
        },
        ports={
            "5672": port,
            "15672": ui_port,
        },
        environment={
            "RABBITMQ_DEFAULT_USER": username,
            "RABBITMQ_DEFAULT_PASS": password,
            "RABBITMQ_DEFAULT_VHOST": "/",
        },
    )
    secho("Container ", nl=False)
    secho(container.short_id, nl=False, fg=colors.GREEN)
    secho(" successfully started")
    wait_healtcheck(docker, container.id)
    print_network_settings(docker, container.id)


@cli.command(help="Run redis container")
def redis(
    name: Optional[str] = Argument(None, help="Name of the container"),
    port: int = Option(6379, help="Port to open for redis protocol"),
    network: str = Option(
        DEFAULT_NETWORK_NAME,
        help="Network name to attach container to",
    ),
    tag: str = Option("7.2", help="Image tag to use"),
):
    docker = from_env()
    img = pull_img(docker, "redis", tag)
    declare_network(docker, network)
    container = docker.containers.run(
        name=name,
        image=img,
        remove=True,
        detach=True,
        network=network,
        hostname=name or "redis",
        healthcheck={
            "test": "redis-cli ping",
            "interval": 1 * 1000 * 1000000,
            "timeout": 3 * 1000 * 1000000,
            "retries": 50,
        },
        ports={
            "6379": port,
        },
    )
    secho("Container ", nl=False)
    secho(container.short_id, nl=False, fg=colors.GREEN)
    secho(" successfully started")
    wait_healtcheck(docker, container.id)
    print_network_settings(docker, container.id)


@cli.command(help="Run scylla container")
def scylla(
    name: Optional[str] = Argument(None, help="Container name"),
    port: int = Option(9042, help="Port to open for scylla"),
    network: str = Option(
        DEFAULT_NETWORK_NAME,
        help="Network name to attach container to",
    ),
    tag: str = Option("5.2", help="Image tag"),
) -> None:
    docker = from_env()
    img = pull_img(docker, "scylladb/scylla", tag)
    declare_network(docker, network)
    volumes = None
    if name is not None:
        volumes = {f"{name}-scylla-db": {"bind": "/var/lib/scylla", "mode": "rw"}}
    container = docker.containers.run(
        name=name,
        image=img,
        remove=True,
        detach=True,
        network=network,
        hostname=name or "scylla",
        command=["--skip-wait-for-gossip-to-settle", "0"],
        healthcheck={
            "test": "cqlsh -e 'select * from system.local'",
            "interval": 5 * 1000 * 1000000,
            "timeout": 5 * 1000 * 1000000,
            "retries": 60,
        },
        ports={
            "9042": port,
        },
        volumes=volumes,
    )
    secho("Container ", nl=False)
    secho(container.short_id, nl=False, fg=colors.GREEN)
    secho(" successfully started")
    wait_healtcheck(docker, container.id)
    print_network_settings(docker, container.id)


@cli.command(help="Run NATS container")
def nats(
    name: Optional[str] = Argument(None, help="Container name"),
    port: int = Option(4222, help="Port to publish for nats protocol"),
    network: str = Option(
        DEFAULT_NETWORK_NAME,
        help="Network name to attach container to",
    ),
    hostname: str = Option("nats", help="Hostname inside the network"),
    tag: str = Option("2.9-alpine", help="Image tag"),
):
    docker = from_env()
    img = pull_img(docker, "nats", tag)
    declare_network(docker, network)
    container = docker.containers.run(
        name=name,
        image=img,
        remove=True,
        detach=True,
        network=network,
        hostname=name or "nats",
        command=["-m", "8222", "--jetstream"],
        healthcheck={
            "test": [
                "CMD",
                "sh",
                "-c",
                "wget http://localhost:8222/healthz -q -O - | xargs | grep ok || exit 1",
            ],
            "interval": 5 * 1000 * 1000000,
            "timeout": 3 * 1000 * 1000000,
            "retries": 20,
        },
        ports={
            "4222": port,
        },
    )
    secho("Container ", nl=False)
    secho(container.short_id, nl=False, fg=colors.GREEN)
    secho(" successfully started")
    wait_healtcheck(docker, container.id)
    print_network_settings(docker, container.id)


def main():
    cli()


if __name__ == "__main__":
    main()
