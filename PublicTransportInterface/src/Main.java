import py4j.GatewayServer;



public class Main {

	/**
	 * @param args
	 */
	public static void main(String[] args) {
        int port = 25333;
        if (args.length > 0) {
            try {
                port = Integer.parseInt(args[0]);
            } catch (NumberFormatException e) {
                System.err.println("Error: Invalid port");
                System.exit(1);
            }
        }
        System.out.println("Gateway Server launched at port " + port);
        QueryData queryData = new QueryData();
        GatewayServer server = new GatewayServer(queryData, port);
        server.start();
	}

}
